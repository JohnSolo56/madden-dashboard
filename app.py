from flask import Flask, render_template
import json
import os
import re
from copy import deepcopy

app = Flask(__name__)

DATA_FILE = "dashboard_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return [], [], "No saved dashboard data yet. Run update_data.py locally and push dashboard_data.json."

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    return data.get("standings", []), data.get("schedule", []), None

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
    w = safe_int(team.get("Wins", 0))
    l = safe_int(team.get("Losses", 0))
    t = safe_int(team.get("Ties", 0))
    total = w + l + t
    return (w + 0.5 * t) / total if total else 0

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
            week = game.get("Week", "?")

            if away and home:
                games.append({"Week": week, "Away": away, "Home": home})

    if games:
        unique = []
        seen = set()

        for game in games:
            key = tuple(sorted([game["Away"], game["Home"]])) + (str(game["Week"]),)
            if key not in seen:
                seen.add(key)
                unique.append(game)

        return unique

    seen = set()

    for team in standings:
        team_name = team.get("Team")
        text = team.get("RemainingGames", "")
        matches = re.findall(r"W(\d+):\s*([^,]+)", text)

        for week, opponent in matches:
            opponent = opponent.strip()
            key = tuple(sorted([team_name, opponent])) + (week,)

            if key not in seen:
                seen.add(key)
                games.append({"Week": week, "Away": team_name, "Home": opponent})

    return games

def build_draft_order(standings, schedule):
    teams = []

    for team in standings:
        item = team.copy()
        item["WinPctCalc"] = record_win_pct(item)
        item["SeedNum"] = safe_int(item.get("Seed", 99), 99)
        item["DiffNum"] = safe_int(item.get("Diff", 0))
        item["PFNum"] = safe_int(item.get("PF", 0))
        item["ConferencePctNum"] = safe_float(item.get("ConferencePct", 0))
        item["DivisionPctNum"] = safe_float(item.get("DivisionPct", 0))
        item["ProjectedSOS"] = safe_float(item.get("AvgDifficulty", 1.0), 1.0)
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
        item["Reason"] = "Non-playoff: record/SOS/tiebreakers" if item["SeedNum"] > 7 else "Projected playoff slot"
        draft_order.append(item)

    return draft_order

def simulate_single_game(standings, winner, loser):
    simulated = deepcopy(standings)
    team_map = {team.get("Team"): team for team in simulated}

    if winner in team_map and loser in team_map:
        team_map[winner]["Wins"] = safe_int(team_map[winner].get("Wins", 0)) + 1
        team_map[loser]["Losses"] = safe_int(team_map[loser].get("Losses", 0)) + 1

    return reseed_after_results(simulated)

def build_scenarios(standings, schedule):
    games = clean_remaining_games(standings, schedule)

    max_games = 20
    games_to_show = games[:max_games]

    current_seed_map = {
        team.get("Team"): safe_int(team.get("Seed", 99), 99)
        for team in standings
    }

    team_results = []

    for team in sorted(standings, key=lambda t: t.get("Team", "")):
        seed = safe_int(team.get("Seed", 99), 99)

        team_results.append({
            "Team": team.get("Team"),
            "PossibleSeeds": str(seed),
            "GuaranteedSeed": seed if seed <= 7 else "",
            "PlayoffOdds": 100 if seed <= 7 else 0
        })

    if_then = []

    for game in games_to_show:
        away = game["Away"]
        home = game["Home"]

        for winner, loser in [(away, home), (home, away)]:
            reseeded = simulate_single_game(standings, winner, loser)
            new_map = {
                team.get("Team"): safe_int(team.get("Seed", 99), 99)
                for team in reseeded
            }

            changed = []

            for team_name, new_seed in new_map.items():
                old_seed = current_seed_map.get(team_name, 99)

                if new_seed != old_seed and new_seed <= 7:
                    changed.append(f"{team_name} moves to #{new_seed}")

            if changed:
                if_then.append({
                    "Game": f"{winner} beats {loser}",
                    "Result": "; ".join(changed[:4])
                })

    if not if_then:
        if_then.append({
            "Game": "No single-game clinch found",
            "Result": "The remaining playoff picture likely depends on multiple game results."
        })

    return {
        "games": games_to_show,
        "total_scenarios": len(games_to_show) * 2,
        "team_results": team_results,
        "if_then": if_then[:100],
        "warning": "Fast mode: this page shows single-game scenario impact only, so Render does not time out."
    }

@app.route("/")
def home():
    standings, schedule, last_error = load_data()

    afc = sorted([t for t in standings if t.get("Conference") == "AFC"], key=lambda x: safe_int(x.get("Seed", 99), 99))
    nfc = sorted([t for t in standings if t.get("Conference") == "NFC"], key=lambda x: safe_int(x.get("Seed", 99), 99))

    return render_template("index.html", afc=afc, nfc=nfc, last_error=last_error)

@app.route("/schedule")
def schedule():
    standings, schedule_rows, last_error = load_data()
    return render_template("schedule.html", schedule=schedule_rows, last_error=last_error)

@app.route("/draft")
def draft():
    standings, schedule_rows, last_error = load_data()
    draft_order = build_draft_order(standings, schedule_rows)
    return render_template("draft.html", draft_order=draft_order, last_error=last_error)

@app.route("/scenarios")
def scenarios():
    standings, schedule_rows, last_error = load_data()
    scenario_data = build_scenarios(standings, schedule_rows)
    return render_template("scenarios.html", scenario_data=scenario_data, last_error=last_error)

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)