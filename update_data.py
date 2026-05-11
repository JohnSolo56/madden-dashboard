import json
from scraper import get_dashboard_data
from app import build_scenarios

standings_df, schedule = get_dashboard_data()

standings = standings_df.to_dict("records")

print("Building full playoff scenario engine...")
scenario_data = build_scenarios(standings, schedule, exhaustive=True)

data = {
    "standings": standings,
    "schedule": schedule,
    "scenario_data": scenario_data
}

with open("dashboard_data.json", "w") as f:
    json.dump(data, f, indent=2)

print("dashboard_data.json updated successfully!")
print(f"Scenario games included: {len(scenario_data.get('games', []))}")
print(f"Total scenarios simulated: {scenario_data.get('total_scenarios', 0)}")