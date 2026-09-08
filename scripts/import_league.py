#!/usr/bin/env python3
"""
Fetch data from a Sleeper fantasy football league and generate:
- teams.json
- schedule.json
- scores.json

Usage:
    python import_league.py <league_id> [output_dir]
"""

import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

import requests

SLEEPER_API = "https://api.sleeper.app/v1"


def fetch_json(endpoint, params=None):
    """Fetch JSON from Sleeper API with rate limiting backoff."""
    url = f"{SLEEPER_API}/{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)
    sys.exit(f"Failed to fetch {endpoint} after 3 attempts.")


def get_regular_season_weeks(settings):
    """Return list of week numbers for the regular season."""
    playoff_start = settings.get("playoff_week_start")
    if playoff_start:
        return list(range(1, playoff_start))
    # default 18 weeks
    return list(range(1, 19))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    league_id = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching data for Sleeper league {league_id} …")

    # ---- League info ----
    league = fetch_json(f"league/{league_id}")
    season = league["season"]
    scoring = league["scoring_settings"]
    regular_weeks = get_regular_season_weeks(league.get("settings", {}))

    # ---- Users ----
    users = fetch_json(f"league/{league_id}/users")
    user_map = {u["user_id"]: u.get("display_name", f"User {u['user_id']}") for u in users}

    # ---- Rosters ----
    rosters = fetch_json(f"league/{league_id}/rosters")
    roster_map = {}
    roster_owner = {}
    for r in rosters:
        rid = r["roster_id"]
        roster_map[rid] = r
        owner_id = r.get("owner_id")
        roster_owner[rid] = user_map.get(owner_id, f"Owner of {rid}")

    # ---- Player database ----
    print("Downloading player database …")
    all_players = fetch_json("players/nfl")

    def player_name(pid):
        p = all_players.get(str(pid))
        if not p:
            return f"Unknown Player ({pid})"
        return (p.get("full_name") or
                f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or
                p.get("name") or
                f"Player {pid}")

    def player_position(pid):
        """Return NFL position (e.g. QB, RB) from player database, or empty string."""
        p = all_players.get(str(pid))
        return p.get("position", "") if p else ""

    # ---- NFL season start date ----
    state = fetch_json("state/nfl")
    season_start_str = state.get("season_start_date") or f"{season}-09-01"
    season_start = datetime.strptime(season_start_str, "%Y-%m-%d")

    # ---- teams.json ----
    teams = {}
    for rid, roster in roster_map.items():
        player_ids = roster.get("players", [])
        roster_players = [{"name": player_name(pid), "id": str(pid)} for pid in player_ids]
        teams[str(rid)] = {
            "name": roster_owner[rid],
            "owner": roster_owner[rid],
            "roster": roster_players,
        }

    # ---- schedule.json & scores.json ----
    schedule = {"weeks": {}}
    scores = {"weeks": {}}

    for week in regular_weeks:
        print(f"Processing week {week} …")
        week_str = str(week)

        matchups = fetch_json(f"league/{league_id}/matchups/{week}")
        if not matchups:
            continue

        week_date = season_start + timedelta(weeks=week - 1)
        schedule["weeks"][week_str] = {
            "date": week_date.strftime("%Y-%m-%d"),
            "matchups": [],
        }

        # Stats for breakdown
        stats_url = f"stats/nfl/regular/{season}/{week}"
        try:
            player_stats = fetch_json(stats_url)
        except SystemExit:
            print(f"Warning: Could not fetch stats for week {week}, skipping breakdown.")
            player_stats = {}

        # Group by matchup_id
        matchup_groups = defaultdict(list)
        for m in matchups:
            matchup_groups[m["matchup_id"]].append(m)

        for mid, pair in matchup_groups.items():
            if len(pair) != 2:
                print(f"Warning: matchup {mid} in week {week} has {len(pair)} teams, skipping.")
                continue
            team1_id = str(pair[0]["roster_id"])
            team2_id = str(pair[1]["roster_id"])
            schedule["weeks"][week_str]["matchups"].append({
                "team1": team1_id,
                "team2": team2_id,
            })

        # ---- Build weekly team scores ----
        week_teams = {}
        for m in matchups:
            roster_id = str(m["roster_id"])
            starters = set(str(s) for s in m.get("starters", []))
            players_points = m.get("players_points", {})

            team_players = {}
            all_roster_players = roster_map[int(roster_id)].get("players", [])
            total_points = 0.0

            for player_id in all_roster_players:
                pid = str(player_id)
                total = players_points.get(str(player_id), 0.0)
                is_starter = pid in starters
                position = player_position(pid) if is_starter else "BENCH"

                # Build breakdown
                breakdown = []
                stats = player_stats.get(pid)
                if stats:
                    for stat, value in stats.items():
                        if stat in scoring and value != 0:
                            points = round(value * scoring[stat], 2)
                            if points != 0:
                                breakdown.append({"name": stat, "score": points})
                if not breakdown:
                    breakdown.append({"name": "total", "score": total})

                team_players[pid] = {
                    "total": total,
                    "breakdown": breakdown,
                    "position": position,
                }

                if position != "BENCH":
                    total_points += total

            week_teams[roster_id] = {"players": team_players, "total": round(total_points, 2)}

        for m in schedule["weeks"][week_str]["matchups"]:
            team1 = str(m["team1"])
            team2 = str(m["team2"])
            s1 = week_teams[team1]["total"]
            s2 = week_teams.get(team2, {}).get("total", 0.0)

            if s1 > s2:
                week_teams[team1]["result"] = "WIN"
                week_teams[team2]["result"] = "LOSS"
            elif s1 < s2:
                week_teams[team1]["result"] = "LOSS"
                week_teams[team2]["result"] = "WIN"
            else:
                week_teams[team1]["result"] = "TIE"
                week_teams[team2]["result"] = "TIE"

        scores["weeks"][week_str] = {"teams": week_teams}

    # ---- Write output ----
    (output_dir / "teams.json").write_text(json.dumps({"teams": teams}, indent=2), encoding="utf-8")
    (output_dir / "schedule.json").write_text(json.dumps(schedule, indent=2), encoding="utf-8")
    (output_dir / "scores.json").write_text(json.dumps(scores, indent=2), encoding="utf-8")

    print(f"Done! Files written to {output_dir.resolve()}")


if __name__ == "__main__":
    main()