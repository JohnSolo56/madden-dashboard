from flask import Flask, render_template
import json
import os
import re

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

def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def record_win_pct(team):
    wins = safe_int(team.get("Wins", 0))
    losses = safe_int(team.get("Losses", 0))
    ties = safe_int(team.get("Ties", 0))

    total = wins + losses + ties

    if total == 0:
        return 0

    return (wins + 0.5 * ties) / total

def calculate_sos(team_name, standings, schedule):
    record_map = {
        team.get("Team"): record_win_pct(team)
        for team in standings
    }

    opponents = []

    for game in schedule:
        away = game.get("Away")
        home = game.get("Home")

        if away == team_name:
            opponents.append(home)

        if home == team_name:
            opponents.append(away)

    if not opponents:
        remaining_text = ""

        for team in standings:
            if team.get("Team") == team_name:
                remaining_text = team.get("RemainingGames", "")
                break

        matches = re.findall(r"W\d+:\s*([^,]+)", remaining_text)

        for match in matches:
            opponents.append(match.strip())

    if not opponents:
        return 1.000

    opponent_pcts = []

    for opponent in opponents:
        opponent_pcts.append(record_map.get(opponent, 0))

    return round(sum(opponent_pcts) / len(opponent_pcts), 3)

def build_draft_order(standings, schedule):
    teams = []

    for team in standings:
        item = team.copy()
        item["WinPctCalc"] = record_win_pct(item)
        item["ProjectedSOS"] = calculate_sos(item.get("Team"), standings, schedule)
        item["SeedNum"] = safe_int(item.get("Seed", 99), 99)
        item["WinsNum"] = safe_int(item.get("Wins", 0))
        item["DiffNum"] = safe_int(item.get("Diff", 0))
        item["PFNum"] = safe_int(item.get("PF", 0))
        item["ConferencePctNum"] = safe_float(item.get("ConferencePct", 0))
        item["DivisionPctNum"] = safe_float(item.get("DivisionPct", 0))
        teams.append(item)

    non_playoff = [t for t in teams if t["SeedNum"] > 7]
    playoff = [t for t in teams if t["SeedNum"] <= 7]

    non_playoff_sorted = sorted(
        non_playoff,
        key=lambda t: (
            t["WinPctCalc"],
            t["ProjectedSOS"],
            t["ConferencePctNum"],
            t["DivisionPctNum"],
            t["DiffNum"],
            t["PFNum"]
        )
    )

    playoff_sorted = sorted(
        playoff,
        key=lambda t: (
            t["SeedNum"] * -1,
            t["WinPctCalc"],
            t["ProjectedSOS"],
            t["DiffNum"],
            t["PFNum"]
        )
    )

    draft_order = []

    for i, team in enumerate(non_playoff_sorted + playoff_sorted, start=1):
        item = team.copy()
        item["Pick"] = i

        if item["SeedNum"] > 7:
            item["Reason"] = "Non-playoff: record, SOS, then NFL-style fallback"
        else:
            item["Reason"] = "Projected playoff slot"

        draft_order.append(item)

    return draft_order

@app.route("/")
def home():
    standings, schedule, last_error = load_data()

    afc = sorted(
        [team for team in standings if team.get("Conference") == "AFC"],
        key=lambda x: safe_int(x.get("Seed", 99), 99)
    )

    nfc = sorted(
        [team for team in standings if team.get("Conference") == "NFC"],
        key=lambda x: safe_int(x.get("Seed", 99), 99)
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

@app.route("/draft")
def draft():
    standings, schedule_rows, last_error = load_data()
    draft_order = build_draft_order(standings, schedule_rows)

    return render_template(
        "draft.html",
        draft_order=draft_order,
        last_error=last_error
    )

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)