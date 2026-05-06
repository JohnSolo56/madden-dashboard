import json
from scraper import get_dashboard_data

standings, schedule = get_dashboard_data()

data = {
    "standings": standings.to_dict("records"),
    "schedule": schedule
}

with open("dashboard_data.json", "w") as f:
    json.dump(data, f, indent=2)

print("dashboard_data.json updated successfully!")