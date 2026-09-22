#!/usr/bin/env python3
"""
Fantasy score generator – best‑ball league with custom scoring pipeline.
DataFrames are global; each rule function extracts its own data.

Usage:
    python generate_scores.py
    python generate_scores.py --week 5
"""

import argparse
import datetime
import json
import sys
from io import StringIO

import numpy as np
import pandas as pd
import requests

# ═══════════════════════════════════════════════════════════════════
# GLOBAL DATAFRAMES
# ═══════════════════════════════════════════════════════════════════
pbp_df = None
snap_df = None
weekly_df = None
players_df = None
team_df = None
game_df = None

# URLs
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.csv"
SNAP_COUNTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{year}.csv"
WEEKLY_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv"
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
TEAM_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{year}.csv"
GAME_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"

TEAM_ABBREVIATIONS = set()

player_map = {}

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_csv(url: str) -> pd.DataFrame:
    print(f"  Downloading {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text), low_memory=False)


# ═══════════════════════════════════════════════════════════════════
# INDIVIDUAL SCORING RULES
# ═══════════════════════════════════════════════════════════════════

def default_sleeper(player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    Sleeper default scoring for all positions.
    Returns (score, [breakdown entries]) starting from zero.
    """
    global weekly_df, team_df

    # 1. Determine player type – defense or individual?
    # Check if player_id is a known team abbreviation (defense)
    if player_id in TEAM_ABBREVIATIONS:
        return defense_score(player_id, week, year)

    # 2. Normal individual player (including kickers)
    wk_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
    if wk_row.empty:
        return 0.0, []
    stats = wk_row.iloc[0].to_dict()

    # 4. Compute Sleeper offensive score (same as before)
    pts = 0.0
    breakdown = []

    # Passing
    pass_yards = stats.get("passing_yards", 0)
    pass_tds = stats.get("pass_touchdown", 0) or stats.get("passing_tds", 0)
    ints = stats.get("interception", 0) or stats.get("interceptions", 0)
    pts_pass_yards = pass_yards * 0.04
    pts_pass_tds = pass_tds * 4
    pts_ints = ints * -1
    if pass_yards:
        breakdown.append({"rule_id": -1, "description": f"{pass_yards} passing yards", "score": round(pts_pass_yards, 2)})
    if pass_tds:
        breakdown.append({"rule_id": -1, "description": f"{pass_tds} passing TDs", "score": round(pts_pass_tds, 2)})
    if ints:
        breakdown.append({"rule_id": -1, "description": f"{ints} interceptions", "score": round(pts_ints, 2)})
    pts += pts_pass_yards + pts_pass_tds + pts_ints

    # Rushing
    rush_yards = stats.get("rushing_yards", 0)
    rush_tds = stats.get("rush_touchdown", 0) or stats.get("rushing_tds", 0)
    pts_rush_yards = rush_yards * 0.1
    pts_rush_tds = rush_tds * 6
    if rush_yards:
        breakdown.append({"rule_id": -1, "description": f"{rush_yards} rushing yards", "score": round(pts_rush_yards, 2)})
    if rush_tds:
        breakdown.append({"rule_id": -1, "description": f"{rush_tds} rushing TDs", "score": round(pts_rush_tds, 2)})
    pts += pts_rush_yards + pts_rush_tds

    # Receiving
    rec_yards = stats.get("receiving_yards", 0)
    rec_tds = stats.get("receiving_touchdown", 0) or stats.get("receiving_tds", 0)
    receptions = stats.get("reception", 0) or stats.get("receptions", 0)
    pts_rec_yards = rec_yards * 0.1
    pts_rec_tds = rec_tds * 6
    pts_receptions = receptions * 1   # PPR
    if rec_yards:
        breakdown.append({"rule_id": -1, "description": f"{rec_yards} receiving yards", "score": round(pts_rec_yards, 2)})
    if rec_tds:
        breakdown.append({"rule_id": -1, "description": f"{rec_tds} receiving TDs", "score": round(pts_rec_tds, 2)})
    if receptions:
        breakdown.append({"rule_id": -1, "description": f"{receptions} receptions", "score": round(pts_receptions, 2)})
    pts += pts_rec_yards + pts_rec_tds + pts_receptions

    # Interceptions
    interceptions = stats.get("passing_interceptions", 0)
    if interceptions:
        pts_int = interceptions * -1
        breakdown.append({"rule_id": -1, "description": f"{interceptions} interceptions", "score": round(pts_int, 2)})
        pts += pts_int

    # Fumbles lost
    fumbles_lost = stats.get("fumble_lost", 0) or stats.get("fumbles_lost", 0)
    if fumbles_lost:
        pts_fum = fumbles_lost * -2
        breakdown.append({"rule_id": -1, "description": f"{fumbles_lost} fumbles lost", "score": round(pts_fum, 2)})
        pts += pts_fum

    # 2‑point conversions
    two_pts_passing = stats.get("passing_2pt_conversion", 0)
    if two_pts_passing:
        pts_2pt_pass = two_pts_passing * 2
        breakdown.append({"rule_id": -1, "description": f"{two_pts_passing} passing two-point conversions", "score": round(pts_2pt_pass, 2)})
        pts += pts_2pt_pass
    two_pts_rushing = stats.get("rushing_2pt_conversion", 0)
    if two_pts_rushing:
        pts_2pt_rush = two_pts_rushing * 2
        breakdown.append({"rule_id": -1, "description": f"{two_pts_rushing} rushing two-point conversions", "score": round(pts_2pt_rush, 2)})
        pts += pts_2pt_rush
    two_pts_receiving = stats.get("receiving_2pt_conversion", 0)
    if two_pts_receiving:
        pts_2pt_rec = two_pts_receiving * 2
        breakdown.append({"rule_id": -1, "description": f"{two_pts_receiving} receiving two-point conversions", "score": round(pts_2pt_rec, 2)})
        pts += pts_2pt_rec

    # PATs (extra points)
    pat_made = stats.get("pat_made", 0)
    if pat_made:
        pts_pat = pat_made * 1
        breakdown.append({"rule_id": -1, "description": f"{pat_made} PATs made", "score": round(pts_pat, 2)})
        pts += pts_pat
    pat_missed = stats.get("pat_missed", 0)
    if pat_missed:
        pts_pat_miss = pat_missed * -1
        breakdown.append({"rule_id": -1, "description": f"{pat_missed} PATs missed", "score": round(pts_pat_miss, 2)})
        pts += pts_pat_miss

    # Field goals made by distance bucket
    fg_buckets = {
        "fg_made_0_19": 3, "fg_made_20_29": 3, "fg_made_30_39": 3,
        "fg_made_40_49": 4, "fg_made_50_59": 5, "fg_made_60_plus": 5
    }
    for col, points_per in fg_buckets.items():
        made = stats.get(col, 0)
        if made:
            pts_fg = made * points_per
            breakdown.append({"rule_id": -1, "description": f"{made} FG {col.replace('fg_made_','').replace('_','-')} yards", "score": round(pts_fg, 2)})
            pts += pts_fg

    # Missed field goals (any distance) = -1
    fg_missed = stats.get("fg_missed", 0)
    if fg_missed:
        pts_fg_miss = fg_missed * -1
        breakdown.append({"rule_id": -1, "description": f"{fg_missed} FG missed", "score": round(pts_fg_miss, 2)})
        pts += pts_fg_miss

    return pts, breakdown


def defense_score(team_abbr: str, week: int, year: int) -> tuple[float, list]:
    """Sleeper team defense scoring from team_stats."""
    global team_df

    team_df_row = team_df[(team_df["team"] == team_abbr) & (team_df["week"] == week)]
    if team_df_row.empty:
        return 0.0, []
    team_row = team_df_row.iloc[0]

    game_df_row = game_df[((game_df["home_team"] == team_abbr) | (game_df["away_team"] == team_abbr)) & (game_df["week"] == week) & (game_df["season"] == year)]
    if game_df_row.empty:
        return 0.0, []
    game_row = game_df_row.iloc[0]

    pts = 0.0
    breakdown = []

    # Sacks (1 point each)  !!! OVERRIDDEN BY TYLER'S RULE !!!
    # sacks = team_row.get("def_sacks", 0)
    # if sacks:
    #     pts_sacks = sacks * 1
    #     breakdown.append({"rule_id": -1, "description": f"{sacks} sacks", "score": round(pts_sacks, 2)})
    #     pts += pts_sacks

    # Interceptions (2 points)
    interceptions = team_row.get("def_interceptions", 0)
    if interceptions:
        pts_int = interceptions * 2
        breakdown.append({"rule_id": -1, "description": f"{interceptions} interceptions", "score": round(pts_int, 2)})
        pts += pts_int

    # Fumble recoveries (2 points)
    fumbles_rec = team_row.get("fumble_recovery_opp", 0)
    if fumbles_rec:
        pts_fr = fumbles_rec * 2
        breakdown.append({"rule_id": -1, "description": f"{fumbles_rec} fumble recoveries", "score": round(pts_fr, 2)})
        pts += pts_fr

    # Defensive TDs (6 points)
    def_tds = team_row.get("def_tds", 0)
    if def_tds:
        pts_td = def_tds * 6
        breakdown.append({"rule_id": -1, "description": f"{def_tds} defensive TDs", "score": round(pts_td, 2)})
        pts += pts_td

    # Safeties (2 points)
    safeties = team_row.get("def_safeties", 0)
    if safeties:
        pts_safety = safeties * 2
        breakdown.append({"rule_id": -1, "description": f"{safeties} safeties", "score": round(pts_safety, 2)})
        pts += pts_safety

    # Points allowed brackets
    points_allowed = game_row.get("away_score", 0) if game_row.get("home_team") == team_abbr else game_row.get("home_score", 0)  # column name might vary
    bracket_pts = 0
    if points_allowed == 0:
        bracket_pts = 10
    elif points_allowed <= 6:
        bracket_pts = 7
    elif points_allowed <= 13:
        bracket_pts = 4
    elif points_allowed <= 17:
        bracket_pts = 1
    elif points_allowed <= 27:
        bracket_pts = 0
    elif points_allowed <= 34:
        bracket_pts = -1
    else:
        bracket_pts = -4

    breakdown.append({"rule_id": -1, "description": f"{points_allowed} points allowed", "score": bracket_pts})
    pts += bracket_pts

    score = round(pts, 2)
    return score, breakdown


def MASON(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    Multiply score by offensive snap percentage.
    """
    global players_df, snap_df, weekly_df, TEAM_ABBREVIATIONS

    # Skip defenses
    if player_id in TEAM_ABBREVIATIONS:
        return score, breakdown

    # Step 1: get pfr_id from players_df using gsis_id
    player_info = players_df[players_df["gsis_id"] == player_id]
    if player_info.empty:
        return score, breakdown
    else:
        wk_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
        if wk_row.empty:
            return score, breakdown
        stats = wk_row.iloc[0].to_dict()
        if stats.get("position") == "K":
            return score, breakdown
        pfr_id = player_info.iloc[0]["pfr_id"]
        if pd.isna(pfr_id) or pfr_id == "":
            snap_pct = 0
        else:
            # Step 2: get snap row by pfr_id and week
            snap_row = snap_df[(snap_df["pfr_player_id"] == pfr_id) & (snap_df["week"] == week)]
            if snap_row.empty:
                snap_pct = 0
            else:
                snap_pct = snap_row.iloc[0]["offense_pct"]

    new_score = round(score * snap_pct, 2)
    breakdown.append({
        "rule_id": 1,
        "description": f"{(snap_pct * 100):.1f}% offensive snaps",
        "score": round(new_score - score, 2)
    })
    return new_score, breakdown

def DYLAN(players_scores: list, roster_slots: list) -> dict:
    """
    Worst ball.
    """
    
    sorted_players = sorted(players_scores, key=lambda x: x["score"], reverse=True)
    used_ids = set()
    slot_assignments = {}

    for allowed_positions in roster_slots:
        best_player = None
        best_score = float("inf")
        for player in sorted_players:
            if player["id"] in used_ids:
                continue
            if player["nfl_position"] in allowed_positions:
                if player["score"] < best_score and player["score"] != 0:
                    best_player = player
                    best_score = player["score"]

        if best_player:
            used_ids.add(best_player["id"])
            label = allowed_positions[0] if len(allowed_positions) == 1 else "/".join(allowed_positions)
            slot_assignments[best_player["id"]] = label

    for player in sorted_players:
        if player["id"] not in slot_assignments:
            slot_assignments[player["id"]] = "BENCH"

    return slot_assignments

def PAYTON(score: float, breakdown: list,
           player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    Score is zero if team lost.
    """
    global weekly_df, game_df

    team = None

    if player_id in TEAM_ABBREVIATIONS:
        team = player_id

    else:
        wk_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
        if wk_row.empty:
            return score, breakdown
        stats = wk_row.iloc[0].to_dict()
        team = stats.get("team")

    game_row = game_df[(game_df["season"] == year) & (game_df["week"] == week) & ((game_df["home_team"] == team) | (game_df["away_team"] == team))]
    if game_row.empty:
        return score, breakdown
    game = game_row.iloc[0].to_dict()
    if (game.get("home_team") == team and game.get("home_score") < game.get("away_score")) or \
       (game.get("away_team") == team and game.get("away_score") < game.get("home_score")):
        breakdown.append({"rule_id": 6, "description": "Team lost", "score": -score})
        score = 0
    return score, breakdown
    

def JAXON(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    -T per TD where T is the number of timeouts each team has left.
    """
    global pbp_df

    pbp_row = pbp_df[((pbp_df["td_player_id"] == player_id) | ((pbp_df["pass_touchdown"] == 1) & (pbp_df["passer_player_id"] == player_id))) & (pbp_df["week"] == week)]
    if pbp_row.empty:
        return score, breakdown

    for _, row in pbp_row.iterrows():
        timeouts = row["home_timeouts_remaining"] + row["away_timeouts_remaining"]
        breakdown.append({"rule_id": 0, "description": f"{timeouts} timeouts remaining during TD", "score": -timeouts})
        score -= timeouts
    return score, breakdown

def TYLER(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    QB +10 per sack, DEF -10 per sack.
    """
    global weekly_df, team_df

    if player_id in TEAM_ABBREVIATIONS:
        team_row = team_df[(team_df["team"] == player_id) & (team_df["week"] == week)]
        if team_row.empty:
            return score, breakdown
        sacks = team_row.iloc[0].get("def_sacks", 0)
        if sacks:
            bonus = -10 * sacks
            breakdown.append({"rule_id": 3, "description": f"{sacks} sacks", "score": bonus})
            score += bonus
        return score, breakdown

    week_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
    if week_row.empty:
        return score, breakdown

    stats = week_row.iloc[0].to_dict()

    sacks = stats.get("sacks_suffered", 0)
    if sacks:
        bonus = 10 * sacks
        breakdown.append({"rule_id": 3, "description": f"Suffered {sacks} sacks", "score": bonus})
        score += bonus
    return score, breakdown

def MARK(score: float, breakdown: list,
         player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    +1 PPR for players who play on a team with a bird mascot.
    """
    global weekly_df
    wk_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
    if wk_row.empty:
        return score, breakdown
    stats = wk_row.iloc[0].to_dict()

    bird_teams = ["ARI", "ATL", "BAL", "PHI", "SEA"]
    team = stats.get("team")
    if team in bird_teams:
        bonus = stats.get("reception", 0) or stats.get("receptions", 0)
        breakdown.append({"rule_id": 2, "description": f"{bonus} receptions for a bird team", "score": bonus})
        score += bonus

    return score, breakdown

def JACOB(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    2x points, +10 points for plays over 20 yards
    """
    global pbp_df

    for _, row in pbp_df[((pbp_df["rusher_player_id"] == player_id) | (pbp_df["lateral_rusher_player_id"] == player_id) | (pbp_df["lateral_receiver_player_id"] == player_id)) & (pbp_df["week"] == week)].iterrows():
        yards = row.get("rushing_yards", 0)
        if yards >= 20:
            bonus = 10
            bonus += row.get("rushing_yards", 0) * 0.1
            if row.get("td_player_id") == player_id:
                bonus += 6
                breakdown.append({"rule_id": 5, "description": f"{yards} yard TD rush", "score": bonus})
            else:
                breakdown.append({"rule_id": 5, "description": f"{yards} yard rush", "score": bonus})
            score += bonus

    for _, row in pbp_df[(pbp_df["receiver_player_id"] == player_id) & (pbp_df["week"] == week)].iterrows():
        yards = row.get("receiving_yards", 0)
        if yards >= 20:
            bonus = 11
            bonus += row.get("receiving_yards", 0) * 0.1
            if row.get("td_player_id") == player_id:
                bonus += 6
                breakdown.append({"rule_id": 5, "description": f"{yards} yard TD reception", "score": bonus})
            else:
                breakdown.append({"rule_id": 5, "description": f"{yards} yard reception", "score": bonus})
            score += bonus

    return score, breakdown

def MATT(score: float, breakdown: list,
             player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    +100 for tackle by QB.
    """
    global weekly_df
    wk_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
    if wk_row.empty:
        return score, breakdown
    stats = wk_row.iloc[0].to_dict()
    tackles = stats.get("tackles", 0)
    if tackles > 0 and (stats.get("position") == "QB"):
        bonus = 100 * tackles
        breakdown.append({"rule_id": 4, "description": f"{tackles} tackles by QB", "score": bonus})
        score += bonus
    return score, breakdown

def Y2023(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    0.5 points per return yard.
    """
    global weekly_df
    wk_row = weekly_df[(weekly_df["player_id"] == player_id) & (weekly_df["week"] == week)]
    if wk_row.empty:
        return score, breakdown
    stats = wk_row.iloc[0].to_dict()

    punt_return_yards = stats.get("punt_return_yards", 0)
    kickoff_return_yards = stats.get("kickoff_return_yards", 0)
    pts_punt_return_yards = punt_return_yards * 0.5
    pts_kickoff_return_yards = kickoff_return_yards * 0.5
    if punt_return_yards:
        breakdown.append({"rule_id": 8, "description": f"{punt_return_yards} punt return yards", "score": round(pts_punt_return_yards, 2)})
    if kickoff_return_yards:
        breakdown.append({"rule_id": 8, "description": f"{kickoff_return_yards} kickoff return yards", "score": round(pts_kickoff_return_yards, 2)})
    score += pts_punt_return_yards + pts_kickoff_return_yards
    
    return score, breakdown

def Y2024(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    x2 points for defense.
    """
    if player_id in TEAM_ABBREVIATIONS:
        breakdown.append({"rule_id": 9, "description": "Defense x2", "score": score})
        score *= 2
    return score, breakdown

def Y2025(score: float, breakdown: list,
          player_id: str, week: int, year: int) -> tuple[float, list]:
    """
    +1 point per sack yard.
    """
    if player_id in TEAM_ABBREVIATIONS:
        global team_df
        team_row = team_df[(team_df["team"] == player_id) & (team_df["week"] == week)]
        if not team_row.empty:
            sack_yards = team_row.iloc[0].get("def_sack_yards", 0)
            if sack_yards:
                breakdown.append({"rule_id": 10, "description": f"{sack_yards} sack yards", "score": sack_yards})
                score += sack_yards

    return score, breakdown



def calculate_score(player_id: str, week: int, year: int) -> tuple[float, list[dict]]:
    """
    Compute fantasy score by chaining rules.
    """
    score, breakdown = default_sleeper(player_id, week, year)
    score, breakdown = Y2023(score, breakdown, player_id, week, year)
    score, breakdown = Y2025(score, breakdown, player_id, week, year)
    score, breakdown = JAXON(score, breakdown, player_id, week, year)
    score, breakdown = TYLER(score, breakdown, player_id, week, year)
    score, breakdown = MARK(score, breakdown, player_id, week, year)
    score, breakdown = JACOB(score, breakdown, player_id, week, year)
    score, breakdown = MATT(score, breakdown, player_id, week, year)
    score, breakdown = MASON(score, breakdown, player_id, week, year)
    score, breakdown = PAYTON(score, breakdown, player_id, week, year)
    score, breakdown = Y2024(score, breakdown, player_id, week, year)

    return score, breakdown


# ═══════════════════════════════════════════════════════════════════
# BEST‑BALL LINEUP OPTIMISATION
# ═══════════════════════════════════════════════════════════════════

def assign_best_ball_positions(players_scores: list, roster_slots: list) -> dict:
    sorted_players = sorted(players_scores, key=lambda x: x["score"], reverse=True)
    used_ids = set()
    slot_assignments = {}

    for allowed_positions in roster_slots:
        best_player = None
        best_score = -float("inf")
        for player in sorted_players:
            if player["id"] in used_ids:
                continue
            if player["nfl_position"] in allowed_positions:
                if player["score"] > best_score:
                    best_player = player
                    best_score = player["score"]

        if best_player:
            used_ids.add(best_player["id"])
            label = allowed_positions[0] if len(allowed_positions) == 1 else "/".join(allowed_positions)
            slot_assignments[best_player["id"]] = label

    for player in sorted_players:
        if player["id"] not in slot_assignments:
            slot_assignments[player["id"]] = "BENCH"

    return slot_assignments


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    global pbp_df, snap_df, weekly_df, players_df, team_df, game_df, TEAM_ABBREVIATIONS, player_map

    parser = argparse.ArgumentParser(description="Generate best‑ball fantasy scores.")
    parser.add_argument("--week", type=int)
    parser.add_argument("--teams", default="teams.json")
    parser.add_argument("--schedule", default="schedule.json")
    parser.add_argument("--player-map", default="player_map.json")
    parser.add_argument("--roster", default="roster.json")
    parser.add_argument("--output", default="scores.json")
    args = parser.parse_args()

    teams_data = load_json(f"2026/{args.teams}")
    schedule_data = load_json(f"2026/{args.schedule}")
    player_map = load_json(args.player_map)
    roster_slots = load_json(f"2026/{args.roster}")

    weeks_to_process = []
    if args.week:
        w = str(args.week)
        if w not in schedule_data["weeks"]:
            sys.exit(f"Week {w} not in schedule.")
        weeks_to_process = [w]
    else:
        weeks_to_process = list(schedule_data["weeks"].keys())

    # Load DataFrames globally
    print("Fetching data …")
    pbp_df = fetch_csv(PBP_URL.format(year=2026))
    snap_df = fetch_csv(SNAP_COUNTS_URL.format(year=2026))
    weekly_df = fetch_csv(WEEKLY_STATS_URL.format(year=2026))
    players_df = fetch_csv(PLAYERS_URL)   # one-time large file
    team_df = fetch_csv(TEAM_STATS_URL.format(year=2026))
    game_df = fetch_csv(GAME_STATS_URL)

    TEAM_ABBREVIATIONS = set(team_df["team"].dropna().unique())
    TEAM_ABBREVIATIONS.add("LAR")
    TEAM_ABBREVIATIONS.add("LA")


    scores = {"weeks": {}}

    for week_str in weeks_to_process:
        if schedule_data["weeks"][week_str]["date"] > datetime.date.today().strftime("%Y-%m-%d"):
            break

        week_int = int(week_str)
        week_scores_teams = {}

        for team_id, team_info in teams_data["teams"].items():
            roster_players = []

            for player_entry in team_info["roster"]:
                internal_id = player_entry["id"]
                nfl_id = resolve_nfl_id(internal_id)
                if not nfl_id:
                    roster_players.append({
                        "id": internal_id,
                        "score": 0,
                        "breakdown": [],
                        "nfl_position": "BENCH",
                    })
                    continue

                # Run scoring pipeline
                total, breakdown = calculate_score(nfl_id, week_int, 2026)

                # Get real NFL position for best‑ball (from weekly stats)
                wk_row = weekly_df[(weekly_df["player_id"] == nfl_id) & (weekly_df["week"] == week_int)]
                nfl_pos = "DEF" if internal_id in TEAM_ABBREVIATIONS else wk_row.iloc[0]["position"] if not wk_row.empty else ""

                roster_players.append({
                    "id": internal_id,
                    "nfl_id": nfl_id,
                    "score": total,
                    "breakdown": breakdown,
                    "nfl_position": nfl_pos,
                })

            # Best‑ball lineup optimisation
            assignment = DYLAN(roster_players, roster_slots)

            team_score = 0
            team_players_scores = {}
            for rp in roster_players:
                team_players_scores[rp["id"]] = {
                    "total": rp["score"],
                    "breakdown": rp["breakdown"],
                    "position": assignment[rp["id"]]
                }
                if assignment[rp["id"]] != "BENCH":
                    team_score += rp["score"]
            week_scores_teams[team_id] = {"players": team_players_scores, "total": round(team_score, 2)}

        current_time = datetime.date.today()
        if current_time.year == 2026 and current_time < (datetime.datetime.strptime(schedule_data["weeks"][week_str]["date"], "%Y-%m-%d").date() + datetime.timedelta(days=6)):
            for team_id in week_scores_teams:
                week_scores_teams[team_id]["result"] = "TBD"
            scores["weeks"][week_str] = {"teams": week_scores_teams}
            continue
        
        for matchup in schedule_data["weeks"][week_str]["matchups"]:
            team_a = matchup["team1"]
            team_b = matchup["team2"]
            score_a = week_scores_teams[team_a]["total"]
            score_b = week_scores_teams[team_b]["total"]
            if score_a > score_b:
                week_scores_teams[team_a]["result"] = "WIN"
                week_scores_teams[team_b]["result"] = "LOSS"
            elif score_b > score_a:
                week_scores_teams[team_b]["result"] = "WIN"
                week_scores_teams[team_a]["result"] = "LOSS"
            else:
                week_scores_teams[team_a]["result"] = "TIE"
                week_scores_teams[team_b]["result"] = "TIE"

        scores["weeks"][week_str] = {"teams": week_scores_teams}

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(make_json_safe(scores), f, indent=2)
    print(f"scores.json written to {args.output}")

def resolve_nfl_id(internal_id: str) -> str:
    """
    Resolve internal player ID to NFL ID using player_map.
    """
    if internal_id in TEAM_ABBREVIATIONS:
        return internal_id

    if internal_id == "LAR":
        return "LA"

    ids = player_map.get(internal_id)
    if not ids:
        return None
    if ids.get("gsis_id"):
        return ids["gsis_id"]
    if ids.get("espn_id"):
        players_df_row = players_df[players_df["espn_id"] == ids["espn_id"]]
        if not players_df_row.empty:
            return players_df_row.iloc[0]["gsis_id"]
    if ids.get("last_name") and ids.get("first_name"):
        players_df_row = players_df[(players_df["last_name"] == ids["last_name"]) & ((players_df["first_name"] == ids["first_name"].split()[0]) | (players_df["common_first_name"] == ids["first_name"].split()[0]))]
        if not players_df_row.empty:
            return players_df_row.iloc[0]["gsis_id"]
    if ids.get("full_name"):
        players_df_row = players_df[players_df["display_name"] == ids["full_name"]]
        if not players_df_row.empty:
            return players_df_row.iloc[0]["gsis_id"]

    print(f"Could not resolve NFL ID for internal ID: {internal_id}")
    print(f"Player map entry: {ids}")

def make_json_safe(obj):
    """Recursively convert numpy/pandas types to native Python types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(i) for i in obj]
    return obj

if __name__ == "__main__":
    main()