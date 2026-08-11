import requests, json

data = requests.get("https://api.sleeper.app/v1/players/nfl").json()
mapping = {}
for sleeper_id, info in data.items():
    gsis = info.get("gsis_id")
    if gsis:
        mapping[sleeper_id] = gsis

with open("player_map.json", "w") as f:
    json.dump(mapping, f, indent=2)