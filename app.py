from flask import Flask, render_template
import json
import os

app = Flask(__name__)

DATA_FILE = "dashboard_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return [], [], "No saved dashboard data yet. Run update_data.py locally and push dashboard_data.json."

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    standings = data.get("standings", [])
    schedule = data.get("schedule", [])

    return standings, schedule, None

@app.route("/")
def home():
    standings, schedule, last_error = load_data()

    afc = sorted(
        [team for team in standings if team.get("Conference") == "AFC"],
        key=lambda x: x.get("Seed", 99)
    )

    nfc = sorted(
        [team for team in standings if team.get("Conference") == "NFC"],
        key=lambda x: x.get("Seed", 99)
    )

    return render_template(
        "index.html",
        afc=afc,
        nfc=nfc,
        last_error=last_error
    )

@app.route("/schedule")
def schedule():
    standings, schedule_rows, last_error = load_data()

    return render_template(
        "schedule.html",
        schedule=schedule_rows,
        last_error=last_error
    )

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)