from flask import Flask, render_template, request
import json
import os
import re
from copy import deepcopy

app = Flask(__name__)

DATA_FILE = "dashboard_data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return [], [], None, "No dashboard data found."

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    standings = data.get("standings", [])
    schedule = data.get("schedule", [])
    scenario_data = data.get("scenario_data", {})

    return standings, schedule, scenario_data, None


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


def sort_for_seed(teams):
    return sorted(
        teams,
        key=lambda t: (
            safe_float(t.get("WinPct", 0)),
            safe_float(t.get("DivisionPct", 0)),
            safe_float(t.get("ConferencePct", 0)),
            safe_int(t.get("Diff", 0)),
            safe_int(t.get("PF", 0))
        ),
        reverse=True
    )


def reseed_after_results(standings):
    teams = deepcopy(standings)

    for team in teams:
        wins = safe_int(team.get("Wins", 0))
        losses = safe_int(team.get("Losses", 0))
        ties = safe_int(team.get("Ties", 0))

        total = wins + losses + ties

        team["WinPct"] = round((wins + 0.5 * ties) / total, 3) if total else 0

    final = []

    for conf in ["AFC", "NFC"]:
        conf_teams = [t for t in teams if t.get("Conference") == conf]

        divisions = sorted(set(t.get("Division") for t in conf_teams))

        division_winners = []

        for division in divisions:
            div_teams = [t for t in conf_teams if t.get("Division") == division]

            if div_teams:
                winner = sort_for_seed(div_teams)[0]
                winner["DivisionWinner"] = True
                division_winners.append(winner)

        division_winners = sort_for_seed(division_winners)

        for i, team in enumerate(division_winners, start=1):
            team["Seed"] = i

        winner_names = set(t.get("Team") for t in division_winners)

        wildcards = [t for t in conf_teams if t.get("Team") not in winner_names]
        wildcards = sort_for_seed(wildcards)

        for i, team in enumerate(wildcards[:3], start=5):
            team["Seed"] = i
            team["DivisionWinner"] = False

        for i, team in enumerate(wildcards[3:], start=8):
            team["Seed"] = i
            team["DivisionWinner"] = False

        final.extend(division_winners + wildcards)

    return final


def clean_remaining_games(standings, schedule):
    games = []

    if schedule:
        for game in schedule:
            away = game.get("Away")
            home = game.get("Home")
            week = str(game.get("Week", "?"))

            if away and home:
                games.append({
                    "Week": week,
                    "Away": away,
                    "Home": home
                })

    unique = []
    seen = set()

    for game in games:
        key = tuple(sorted([game["Away"], game["Home"]])) + (game["Week"],)

        if key not in seen:
            seen.add(key)
            unique.append(game)

    return unique


def apply_selected_results(standings, selected_winners, games):
    simulated = deepcopy(standings)

    team_map = {
        team.get("Team"): team
        for team in simulated
    }

    for index, game in enumerate(games):
        winner = selected_winners.get(f"game_{index}")

        if not winner:
            continue

        away = game["Away"]
        home = game["Home"]

        loser = home if winner == away else away

        if winner in team_map:
            team_map[winner]["Wins"] = safe_int(team_map[winner].get("Wins", 0)) + 1

        if loser in team_map:
            team_map[loser]["Losses"] = safe_int(team_map[loser].get("Losses", 0)) + 1

    reseeded = reseed_after_results(simulated)

    afc = sorted(
        [t for t in reseeded if t.get("Conference") == "AFC"],
        key=lambda x: safe_int(x.get("Seed", 99))
    )

    nfc = sorted(
        [t for t in reseeded if t.get("Conference") == "NFC"],
        key=lambda x: safe_int(x.get("Seed", 99))
    )

    return afc, nfc


@app.route("/")
def home():
    standings, schedule, scenario_data, last_error = load_data()

    afc = sorted(
        [team for team in standings if team.get("Conference") == "AFC"],
        key=lambda x: safe_int(x.get("Seed", 99))
    )

    nfc = sorted(
        [team for team in standings if team.get("Conference") == "NFC"],
        key=lambda x: safe_int(x.get("Seed", 99))
    )

    return render_template(
        "index.html",
        afc=afc,
        nfc=nfc,
        last_error=last_error
    )


@app.route("/schedule")
def schedule():
    standings, schedule_rows, scenario_data, last_error = load_data()

    return render_template(
        "schedule.html",
        schedule=schedule_rows,
        last_error=last_error
    )


@app.route("/draft")
def draft():
    standings, schedule_rows, scenario_data, last_error = load_data()

    return render_template(
        "draft.html",
        draft_order=standings,
        last_error=last_error
    )


@app.route("/scenarios", methods=["GET", "POST"])
def scenarios():
    standings, schedule_rows, scenario_data, last_error = load_data()

    games = clean_remaining_games(standings, schedule_rows)

    afc_results = None
    nfc_results = None

    selected_winners = {}

    if request.method == "POST":
        selected_winners = request.form.to_dict()

        afc_results, nfc_results = apply_selected_results(
            standings,
            selected_winners,
            games
        )

    return render_template(
        "scenarios.html",
        games=games,
        afc_results=afc_results,
        nfc_results=nfc_results,
        selected_winners=selected_winners,
        last_error=last_error
    )


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    app.run(debug=True)