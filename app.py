from flask import Flask, render_template
import json
import os
import re
import itertools
from copy import deepcopy

app = Flask(__name__)

DATA_FILE = "dashboard_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return [], [], None, "No saved dashboard data yet. Run update_data.py locally and push dashboard_data.json."

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    standings = data.get("standings", [])
    schedule = data.get("schedule", [])
    scenario_data = data.get("scenario_data")

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

        for index, team in enumerate(division_winners, start=1):
            team["Seed"] = index

        winner_names = set(t.get("Team") for t in division_winners)

        wildcards = [t for t in conf_teams if t.get("Team") not in winner_names]
        wildcards = sort_for_seed(wildcards)

        for index, team in enumerate(wildcards[:3], start=5):
            team["Seed"] = index
            team["DivisionWinner"] = False

        for index, team in enumerate(wildcards[3:], start=8):
            team["Seed"] = index
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
                games.append({
                    "Week": str(week),
                    "Away": away,
                    "Home": home
                })

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
                games.append({
                    "Week": week,
                    "Away": team_name,
                    "Home": opponent
                })

    return games

def build_scenarios(standings, schedule, exhaustive=False):
    games = clean_remaining_games(standings, schedule)

    if not games:
        return {
            "games": [],
            "total_scenarios": 0,
            "team_results": [],
            "if_then": [
                {
                    "Game": "No remaining games found",
                    "Result": "The scraper did not find remaining games in dashboard_data.json."
                }
            ],
            "warning": "No remaining games were available."
        }

    max_games = 22

    if len(games) > max_games:
        return {
            "games": games,
            "total_scenarios": 0,
            "team_results": [],
            "if_then": [
                {
                    "Game": "Too many games to simulate",
                    "Result": f"{len(games)} games were found. That would require {2 ** len(games):,} scenarios, which is too many."
                }
            ],
            "warning": f"Too many games found for exhaustive simulation: {len(games)}."
        }

    team_seed_counts = {}
    team_playoff_counts = {}
    team_total_counts = {}

    for team in standings:
        name = team.get("Team")
        team_seed_counts[name] = {}
        team_playoff_counts[name] = 0
        team_total_counts[name] = 0

    scenario_records = []
    total_scenarios = 0

    for combo in itertools.product([0, 1], repeat=len(games)):
        total_scenarios += 1

        simulated = deepcopy(standings)
        team_map = {team.get("Team"): team for team in simulated}
        outcome_map = {}

        for result, game in zip(combo, games):
            away = game["Away"]
            home = game["Home"]

            if result == 0:
                winner = away
                loser = home
            else:
                winner = home
                loser = away

            game_key = f"W{game['Week']}: {away} vs {home}"
            outcome_map[game_key] = winner

            if winner in team_map and loser in team_map:
                team_map[winner]["Wins"] = safe_int(team_map[winner].get("Wins", 0)) + 1
                team_map[loser]["Losses"] = safe_int(team_map[loser].get("Losses", 0)) + 1

        reseeded = reseed_after_results(simulated)

        seed_map = {}

        for team in reseeded:
            name = team.get("Team")
            seed = safe_int(team.get("Seed", 99), 99)

            seed_map[name] = seed
            team_total_counts[name] += 1
            team_seed_counts[name][seed] = team_seed_counts[name].get(seed, 0) + 1

            if seed <= 7:
                team_playoff_counts[name] += 1

        scenario_records.append({
            "outcomes": outcome_map,
            "seeds": seed_map
        })

    team_results = []

    for team_name in sorted(team_seed_counts.keys()):
        counts = team_seed_counts[team_name]
        possible_seeds = sorted(counts.keys())

        guaranteed_seed = ""
        if len(possible_seeds) == 1 and possible_seeds[0] <= 7:
            guaranteed_seed = possible_seeds[0]

        playoff_odds = round((team_playoff_counts[team_name] / total_scenarios) * 100, 1) if total_scenarios else 0

        team_results.append({
            "Team": team_name,
            "PossibleSeeds": ", ".join(str(seed) for seed in possible_seeds),
            "GuaranteedSeed": guaranteed_seed,
            "PlayoffOdds": playoff_odds
        })

    if_then = []

    for game in games:
        game_key = f"W{game['Week']}: {game['Away']} vs {game['Home']}"

        for winner in [game["Away"], game["Home"]]:
            matching = [
                scenario
                for scenario in scenario_records
                if scenario["outcomes"].get(game_key) == winner
            ]

            if not matching:
                continue

            seed_options_by_team = {}

            for scenario in matching:
                for team_name, seed in scenario["seeds"].items():
                    if team_name not in seed_options_by_team:
                        seed_options_by_team[team_name] = set()

                    seed_options_by_team[team_name].add(seed)

            guarantees = []

            for team_name, seeds in seed_options_by_team.items():
                if len(seeds) == 1:
                    seed = list(seeds)[0]

                    if seed <= 7:
                        guarantees.append(f"{team_name} guaranteed #{seed} seed")

            if guarantees:
                if_then.append({
                    "Game": f"{winner} wins {game_key}",
                    "Result": "; ".join(guarantees[:8])
                })

    if not if_then:
        if_then.append({
            "Game": "No single-game guarantees found",
            "Result": "The playoff picture depends on combinations of multiple games."
        })

    return {
        "games": games,
        "total_scenarios": total_scenarios,
        "team_results": team_results,
        "if_then": if_then,
        "warning": ""
    }

@app.route("/")
def home():
    standings, schedule, scenario_data, last_error = load_data()

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

@app.route("/scenarios")
def scenarios():
    standings, schedule_rows, scenario_data, last_error = load_data()

    if scenario_data is None:
        scenario_data = build_scenarios(standings, schedule_rows, exhaustive=False)

    return render_template(
        "scenarios.html",
        scenario_data=scenario_data,
        last_error=last_error
    )

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)