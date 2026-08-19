import requests, json

data = requests.get("https://api.sleeper.app/v1/players/nfl").json()
mapping = {}
for sleeper_id, info in data.items():
    mapping[sleeper_id] = {}
    fullname = info.get("full_name")
    if fullname:
        mapping[sleeper_id]["full_name"] = fullname
    lastname = info.get("last_name")
    if lastname:
        mapping[sleeper_id]["last_name"] = lastname
    firstname = info.get("first_name")
    if firstname:
        mapping[sleeper_id]["first_name"] = firstname
    gsis = info.get("gsis_id")
    if gsis:
        mapping[sleeper_id]["gsis_id"] = gsis
    espn = info.get("espn_id")
    if espn:
        mapping[sleeper_id]["espn_id"] = espn
    rotowire = info.get("rotowire_id")
    if rotowire:
        mapping[sleeper_id]["rotowire_id"] = rotowire
    fantasy_data = info.get("fantasy_data_id")
    if fantasy_data:
        mapping[sleeper_id]["fantasy_data_id"] = fantasy_data
    kalshi = info.get("kalshi_id")
    if kalshi:
        mapping[sleeper_id]["kalshi_id"] = kalshi
    opta = info.get("opta_id")
    if opta:
        mapping[sleeper_id]["opta_id"] = opta
    yahoo = info.get("yahoo_id")
    if yahoo:
        mapping[sleeper_id]["yahoo_id"] = yahoo
    pandascore = info.get("pandascore_id")
    if pandascore:
        mapping[sleeper_id]["pandascore_id"] = pandascore
    oddsjam = info.get("oddsjam_id")
    if oddsjam:
        mapping[sleeper_id]["oddsjam_id"] = oddsjam
    sportsradar = info.get("sportsradar_id")
    if sportsradar:
        mapping[sleeper_id]["sportsradar_id"] = sportsradar
    rotoworld = info.get("rotoworld_id")
    if rotoworld:
        mapping[sleeper_id]["rotoworld_id"] = rotoworld
    swish = info.get("swish_id")
    if swish:
        mapping[sleeper_id]["swish_id"] = swish

with open("player_map.json", "w") as f:
    json.dump(mapping, f, indent=2)