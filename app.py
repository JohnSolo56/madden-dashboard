from flask import Flask, render_template, request
import json
import os
from copy import deepcopy

app = Flask(__name__)

DATA_FILE = "dashboard_data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return [], [], {}, "No dashboard data found."

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


def normalize_team(team):
    item = team.copy()

    item["Wins"] = safe_int(item.get("Wins", 0))
    item["Losses"] = safe_int(item.get("Losses", 0))
    item["Ties"] = safe_int(item.get("Ties", 0))
    item["Diff"] = safe_int(item.get("Diff", 0))
    item["PF"] = safe_int(item.get("PF", 0))
    item["Seed"] = safe_int(item.get("Seed", 99), 99)

    item["DivisionPct"] = safe_float(item.get("DivisionPct", 0))
    item["ConferencePct"] = safe_float(item.get("ConferencePct", 0))

    total = item["Wins"] + item["Losses"] + item["Ties"]
    item["WinPct"] = round((item["Wins"] + 0.5 * item["Ties"]) / total, 3) if total else 0

    item["Record"] = (
        f"{item['Wins']}-{item['Losses']}"
        if item["Ties"] == 0
        else f"{item['Wins']}-{item['Losses']}-{item['Ties']}"
    )

    return item


def normalize_standings(standings):
    return [normalize_team(team) for team in standings]


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


def record_win_pct(team):
    item = normalize_team(team)
    return item["WinPct"]


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
        return 1.000

    opponent_pcts = []

    for opponent in opponents:
        opponent_pcts.append(record_map.get(opponent, 0))

    return round(sum(opponent_pcts) / len(opponent_pcts), 3)


def build_draft_order(standings, schedule):
    teams = []

    for team in normalize_standings(standings):
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


def reseed_after_results(standings):
    teams = normalize_standings(deepcopy(standings))

    final = []

    for conf in ["AFC", "NFC"]:
        conf_teams = [
            team for team in teams
            if team.get("Conference") == conf
        ]

        divisions = sorted(
            set(team.get("Division") for team in conf_teams)
        )

        division_winners = []

        for division in divisions:
            div_teams = [
                team for team in conf_teams
                if team.get("Division") == division
            ]

            if not div_teams:
                continue

            winner = sort_for_seed(div_teams)[0]
            winner["DivisionWinner"] = True
            division_winners.append(winner)

        division_winners = sort_for_seed(division_winners)

        for seed, team in enumerate(division_winners, start=1):
            team["Seed"] = seed

        winner_names = set(team.get("Team") for team in division_winners)

        wildcards = [
            team for team in conf_teams
            if team.get("Team") not in winner_names
        ]

        wildcards = sort_for_seed(wildcards)

        for seed, team in enumerate(wildcards[:3], start=5):
            team["Seed"] = seed
            team["DivisionWinner"] = False

        for seed, team in enumerate(wildcards[3:], start=8):
            team["Seed"] = seed
            team["DivisionWinner"] = False

        final.extend(division_winners)
        final.extend(wildcards)

    return final


def clean_remaining_games(standings, schedule):
    games = []
    seen = set()

    for game in schedule:
        away = game.get("Away")
        home = game.get("Home")
        week = str(game.get("Week", "?"))

        if not away or not home:
            continue

        key = tuple(sorted([away, home])) + (week,)

        if key in seen:
            continue

        seen.add(key)

        games.append({
            "Week": week,
            "Away": away,
            "Home": home
        })

    return games


def apply_selected_results(standings, selected_winners, games):
    simulated = normalize_standings(deepcopy(standings))

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

        if winner in team_map:
            team_map[winner] = normalize_team(team_map[winner])

        if loser in team_map:
            team_map[loser] = normalize_team(team_map[loser])

    reseeded = reseed_after_results(list(team_map.values()))

    afc = sorted(
        [team for team in reseeded if team.get("Conference") == "AFC"],
        key=lambda x: safe_int(x.get("Seed", 99), 99)
    )

    nfc = sorted(
        [team for team in reseeded if team.get("Conference") == "NFC"],
        key=lambda x: safe_int(x.get("Seed", 99), 99)
    )

    return afc, nfc


@app.route("/")
def home():
    standings, schedule, scenario_data, last_error = load_data()

    afc = sorted(
        [team for team in normalize_standings(standings) if team.get("Conference") == "AFC"],
        key=lambda x: safe_int(x.get("Seed", 99), 99)
    )

    nfc = sorted(
        [team for team in normalize_standings(standings) if team.get("Conference") == "NFC"],
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
    standings, schedule_rows, scenario_data, last_error = load_data()

    return render_template(
        "schedule.html",
        schedule=schedule_rows,
        last_error=last_error
    )


@app.route("/draft")
def draft():
    standings, schedule_rows, scenario_data, last_error = load_data()
    draft_order = build_draft_order(standings, schedule_rows)

    return render_template(
        "draft.html",
        draft_order=draft_order,
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