import json
from scraper import get_dashboard_data

standings_df, schedule = get_dashboard_data()

data = {
    "standings": standings_df.to_dict("records"),
    "schedule": schedule
}

with open("dashboard_data.json", "w") as f:
    json.dump(data, f, indent=2)

print("dashboard_data.json updated successfully!")
print(f"Schedule games included: {len(schedule)}")