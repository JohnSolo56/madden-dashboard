# scraper.py
# LOCAL VERSION
# Remaining games logic:
# Only Week 15-18 games with an actual visible score of 0-0 are counted as remaining.

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import re

CHROMEDRIVER_PATH = "chromedriver.exe"

STANDINGS_URL = "https://neonsportz.com/leagues/JD/standings"
GAMES_URL = "https://neonsportz.com/leagues/JD/games"

REGULAR_SEASON_GAMES = 17
WEEKS_TO_CHECK = [15, 16, 17, 18]

DIVISIONS = {
    "Bills": "AFC East", "Dolphins": "AFC East", "Patriots": "AFC East", "Bisons": "AFC East",
    "Ravens": "AFC North", "Bengals": "AFC North", "Browns": "AFC North", "Steelers": "AFC North",
    "Texans": "AFC South", "Colts": "AFC South", "Jaguars": "AFC South", "Titans": "AFC South",
    "Chiefs": "AFC West", "Raiders": "AFC West", "Chargers": "AFC West", "Oilers": "AFC West",

    "Cowboys": "NFC East", "Giants": "NFC East", "Eagles": "NFC East", "Commanders": "NFC East",
    "Bears": "NFC North", "Lions": "NFC North", "Packers": "NFC North", "Vikings": "NFC North",
    "Falcons": "NFC South", "Saints": "NFC South", "Buccaneers": "NFC South", "Armadillos": "NFC South",
    "Cardinals": "NFC West", "Rams": "NFC West", "49ers": "NFC West", "Seahawks": "NFC West",
}

ALL_TEAMS = set(DIVISIONS.keys())

CITY_TO_TEAM = {
    "Dallas": "Cowboys",
    "Washington": "Commanders",
    "Philadelphia": "Eagles",
    "Tennessee": "Titans",
    "Atlanta": "Falcons",
    "Minnesota": "Vikings",
    "Baltimore": "Ravens",
    "Pittsburgh": "Steelers",
    "Austin": "Armadillos",
    "Detroit": "Lions",
    "Buffalo": "Bills",
    "Miami": "Dolphins",
    "Cleveland": "Browns",
    "Tampa Bay": "Buccaneers",
    "Green Bay": "Packers",
    "New Orleans": "Saints",
    "Kansas City": "Chiefs",
    "Chicago": "Bears",
    "Rio De Janeiro": "Bisons",
    "Las Vegas": "Raiders",
    "Arizona": "Cardinals",
    "San Francisco": "49ers",
    "Seattle": "Seahawks",
    "Indianapolis": "Colts",
    "New York": "Giants",
    "Cincinnati": "Bengals",
    "Jacksonville": "Jaguars",
    "New England": "Patriots",
    "Houston": "Oilers",
}

def get_conference(team):
    division = DIVISIONS.get(team, "")
    if division.startswith("AFC"):
        return "AFC"
    if division.startswith("NFC"):
        return "NFC"
    return "Unknown"

def record_pct(record):
    parts = record.split("-")
    wins = int(parts[0])
    losses = int(parts[1])
    ties = int(parts[2]) if len(parts) > 2 else 0
    total = wins + losses + ties
    return (wins + 0.5 * ties) / total if total else 0

def create_driver():
    service = Service(CHROMEDRIVER_PATH)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 25)

    return driver, wait

def scrape_standings(driver, wait):
    driver.get(STANDINGS_URL)

    wait.until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr"))
    )

    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    teams = []

    for row in rows:
        cols = [
            c.text.strip()
            for c in row.find_elements(By.TAG_NAME, "td")
            if c.text.strip()
        ]

        if len(cols) < 13:
            continue

        team = cols[0].replace(" - X", "").replace(" - Y", "").strip()

        if team not in DIVISIONS:
            continue

        wins = int(cols[1])
        losses = int(cols[2])
        ties = int(cols[3])

        games_left = max(0, REGULAR_SEASON_GAMES - wins - losses - ties)

        teams.append({
            "Conference": get_conference(team),
            "Division": DIVISIONS[team],
            "Team": team,
            "Wins": wins,
            "Losses": losses,
            "Ties": ties,
            "Record": f"{wins}-{losses}" if ties == 0 else f"{wins}-{losses}-{ties}",
            "WinPct": float(cols[4]),
            "Home": cols[5],
            "Away": cols[6],
            "DivisionRecord": cols[7],
            "ConferenceRecord": cols[8],
            "DivisionPct": record_pct(cols[7]),
            "ConferencePct": record_pct(cols[8]),
            "PF": int(cols[9]),
            "PA": int(cols[10]),
            "Diff": int(cols[11]),
            "Streak": cols[12],
            "Seed": 99,
            "DivisionWinner": False,
            "Status": "",
            "MagicNumber": "",
            "Remaining": games_left,
            "RemainingGames": "None",
            "AvgDifficulty": 0
        })

    return pd.DataFrame(teams)

def teams_from_text(text):
    found = []

    for team in ALL_TEAMS:
        if re.search(rf"\b{re.escape(team)}\b", text, re.IGNORECASE):
            found.append(team)

    for city, team in CITY_TO_TEAM.items():
        if re.search(rf"\b{re.escape(city)}\b", text, re.IGNORECASE):
            if team not in found:
                found.append(team)

    return list(dict.fromkeys(found))

def row_has_0_0_score(text):
    """
    Only count a game as remaining if the row visibly has a 0-0 style score.

    Accepted:
    - 0-0
    - 0 - 0
    - 0–0
    - 0 vs 0

    Rejected:
    - 34-21
    - 24 vs 17
    - anything without a clear 0-0 score
    """

    clean = text.replace("–", "-").replace("—", "-")

    # Most normal score displays: 0-0 or 0 - 0
    if re.search(r"\b0\s*-\s*0\b", clean):
        return True

    # NeonSportz style sometimes has "0 vs 0"
    if re.search(r"\b0(?:\.0+)?\s+vs\s+0(?:\.0+)?\b", clean, re.IGNORECASE):
        return True

    return False

def game_is_unplayed(text):
    lower = text.lower()

    # If it clearly says final/completed, never count it.
    blocked_words = [
        "final",
        "completed",
        "played",
        "recap",
        "box score"
    ]

    for word in blocked_words:
        if word in lower:
            return False

    return row_has_0_0_score(text)

def set_week(driver, week):
    try:
        dropdowns = driver.find_elements(By.XPATH, "//*[contains(text(), 'WEEK')]")

        for item in dropdowns:
            if "WEEK" in item.text.upper():
                driver.execute_script("arguments[0].click();", item)
                time.sleep(1)
                break

        option = driver.find_element(By.XPATH, f"//*[contains(text(), 'WEEK {week}')]")
        driver.execute_script("arguments[0].click();", option)
        time.sleep(4)
        return True

    except Exception:
        return False

def scrape_remaining_games(driver):
    all_games = []

    driver.get(GAMES_URL)
    time.sleep(5)

    for week in WEEKS_TO_CHECK:
        set_week(driver, week)
        time.sleep(3)

        rows = driver.find_elements(By.CSS_SELECTOR, "tr")

        for row in rows:
            text = row.text.strip()

            if not text:
                continue

            if not game_is_unplayed(text):
                continue

            teams = teams_from_text(text)

            if len(teams) < 2:
                continue

            team1 = teams[0]
            team2 = teams[1]

            key = (week, tuple(sorted([team1, team2])))

            if key not in all_games:
                all_games.append(key)

    return [(g[0], g[1][0], g[1][1]) for g in all_games]

def sort_teams(df):
    return df.sort_values(
        by=["WinPct", "DivisionPct", "ConferencePct", "Diff", "PF"],
        ascending=[False, False, False, False, False]
    )

def apply_nfl_seeding(df):
    final = []

    for conf in ["AFC", "NFC"]:
        conf_df = df[df["Conference"] == conf].copy()

        winners = []

        for division in sorted(conf_df["Division"].unique()):
            div_df = conf_df[conf_df["Division"] == division].copy()
            winner = sort_teams(div_df).iloc[0].copy()
            winner["DivisionWinner"] = True
            winners.append(winner)

        winners_df = sort_teams(pd.DataFrame(winners))
        winners_df["Seed"] = range(1, len(winners_df) + 1)

        winner_teams = set(winners_df["Team"])

        wildcards = conf_df[~conf_df["Team"].isin(winner_teams)].copy()
        wildcards = sort_teams(wildcards).head(3)
        wildcards["Seed"] = range(5, 5 + len(wildcards))
        wildcards["DivisionWinner"] = False

        playoff = pd.concat([winners_df, wildcards])

        others = conf_df[~conf_df["Team"].isin(set(playoff["Team"]))].copy()
        others = sort_teams(others)
        others["Seed"] = range(8, 8 + len(others))
        others["DivisionWinner"] = False

        final.append(pd.concat([playoff, others]).sort_values("Seed"))

    return pd.concat(final)

def calculate_difficulty(record):
    wins, losses = record.split("-")[:2]
    wins = int(wins)
    losses = int(losses)
    total = wins + losses
    return wins / total if total else 0

def add_status_and_magic_numbers(df):
    df = df.copy()

    for conf in ["AFC", "NFC"]:
        conf_df = df[df["Conference"] == conf].copy()

        playoff_cutoff = conf_df[conf_df["Seed"] == 7]
        eighth = conf_df[conf_df["Seed"] == 8]
        seed_1 = conf_df[conf_df["Seed"] == 1]

        cutoff_wins = int(playoff_cutoff.iloc[0]["Wins"]) if not playoff_cutoff.empty else 0
        eighth_max = int(eighth.iloc[0]["Wins"] + eighth.iloc[0]["Remaining"]) if not eighth.empty else 0
        top_team = seed_1.iloc[0]["Team"] if not seed_1.empty else None

        for idx, row in conf_df.iterrows():
            status = ""

            if row["Seed"] <= 7:
                status = "In Playoffs"

            if row["DivisionWinner"]:
                status = "Division Leader"

            if row["Team"] == top_team:
                status = "#1 Seed"

            max_wins = row["Wins"] + row["Remaining"]

            if max_wins < cutoff_wins:
                status = "Eliminated"

            magic = max(0, eighth_max + 1 - row["Wins"]) if row["Seed"] <= 7 else ""

            df.loc[idx, "Status"] = status
            df.loc[idx, "MagicNumber"] = str(magic)

    return df

def build_schedule_rows(games, standings):
    record_map = {row["Team"]: row["Record"] for _, row in standings.iterrows()}
    rows = []

    for week, team1, team2 in games:
        team1_record = record_map.get(team1, "0-0")
        team2_record = record_map.get(team2, "0-0")

        difficulty = round(
            (calculate_difficulty(team1_record) + calculate_difficulty(team2_record)) / 2,
            3
        )

        rows.append({
            "Week": week,
            "Away": team1,
            "Home": team2,
            "AwayRecord": team1_record,
            "HomeRecord": team2_record,
            "Difficulty": difficulty,
            "Score": "0-0",
            "Status": "Unplayed"
        })

    return rows

def get_dashboard_data():
    driver, wait = create_driver()

    try:
        standings = scrape_standings(driver, wait)
        games = scrape_remaining_games(driver)
    finally:
        driver.quit()

    opponent_map = {team: [] for team in standings["Team"]}

    for week, team1, team2 in games:
        if team1 in opponent_map:
            opponent_map[team1].append(f"W{week}: {team2}")

        if team2 in opponent_map:
            opponent_map[team2].append(f"W{week}: {team1}")

    record_map = {row["Team"]: row["Record"] for _, row in standings.iterrows()}

    remaining_lists = []
    difficulty_scores = []

    for _, row in standings.iterrows():
        team = row["Team"]
        games_left = opponent_map.get(team, [])

        if games_left:
            games_left = sorted(
                games_left,
                key=lambda x: int(x.split(":")[0].replace("W", ""))
            )

            remaining_lists.append(", ".join(games_left))

            scores = []

            for game in games_left:
                opponent = game.split(": ")[1]
                scores.append(calculate_difficulty(record_map.get(opponent, "0-0")))

            difficulty_scores.append(round(sum(scores) / len(scores), 3))

        else:
            if int(row["Remaining"]) > 0:
                remaining_lists.append("No 0-0 game found")
            else:
                remaining_lists.append("None")

            difficulty_scores.append(0)

    standings["RemainingGames"] = remaining_lists
    standings["AvgDifficulty"] = difficulty_scores

    standings = apply_nfl_seeding(standings)
    standings = add_status_and_magic_numbers(standings)

    schedule_rows = build_schedule_rows(games, standings)

    return standings, schedule_rows

def get_fallback_dashboard_data():
    rows = []

    for team, division in DIVISIONS.items():
        conference = "AFC" if division.startswith("AFC") else "NFC"

        rows.append({
            "Conference": conference,
            "Division": division,
            "Team": team,
            "Wins": 0,
            "Losses": 0,
            "Ties": 0,
            "Record": "0-0",
            "WinPct": 0,
            "Home": "0-0-0",
            "Away": "0-0-0",
            "DivisionRecord": "0-0-0",
            "ConferenceRecord": "0-0-0",
            "DivisionPct": 0,
            "ConferencePct": 0,
            "PF": 0,
            "PA": 0,
            "Diff": 0,
            "Streak": "",
            "Seed": 99,
            "DivisionWinner": False,
            "Status": "Needs Refresh",
            "MagicNumber": "",
            "Remaining": REGULAR_SEASON_GAMES,
            "RemainingGames": "Needs Refresh",
            "AvgDifficulty": 0
        })

    df = pd.DataFrame(rows)
    df = apply_nfl_seeding(df)

    return df, []

def get_league_data():
    standings, _ = get_dashboard_data()
    return standings