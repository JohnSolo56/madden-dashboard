from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import re

STANDINGS_URL = "https://neonsportz.com/leagues/JD/standings"
GAMES_URL = "https://neonsportz.com/leagues/JD/games"

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

def create_driver():
    chrome_options = Options()

    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=chrome_options)

    wait = WebDriverWait(driver, 20)

    return driver, wait

def get_conference(team):
    div = DIVISIONS.get(team, "")
    if div.startswith("AFC"):
        return "AFC"
    return "NFC"

def scrape_standings(driver, wait):
    driver.get(STANDINGS_URL)

    wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "table tbody tr")
        )
    )

    teams = []

    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")

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

        teams.append({
            "Conference": get_conference(team),
            "Division": DIVISIONS[team],
            "Team": team,
            "Wins": int(cols[1]),
            "Losses": int(cols[2]),
            "Record": f"{cols[1]}-{cols[2]}",
            "WinPct": float(cols[4]),
            "Diff": int(cols[11]),
            "Streak": cols[12],
            "Seed": 99,
            "DivisionWinner": False,
        })

    return pd.DataFrame(teams)

def sort_teams(df):
    return df.sort_values(
        by=["WinPct", "Diff"],
        ascending=[False, False]
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

        wildcards = conf_df[
            ~conf_df["Team"].isin(winner_teams)
        ].copy()

        wildcards = sort_teams(wildcards).head(3)

        wildcards["Seed"] = range(5, 5 + len(wildcards))

        playoff = pd.concat([winners_df, wildcards])

        others = conf_df[
            ~conf_df["Team"].isin(set(playoff["Team"]))
        ].copy()

        others = sort_teams(others)

        others["Seed"] = range(8, 8 + len(others))

        final.append(
            pd.concat([playoff, others]).sort_values("Seed")
        )

    return pd.concat(final)

def get_dashboard_data():
    driver, wait = create_driver()

    standings = scrape_standings(driver, wait)

    driver.quit()

    standings["Remaining"] = 0
    standings["RemainingGames"] = "Coming Soon"
    standings["AvgDifficulty"] = 0

    standings = apply_nfl_seeding(standings)

    return standings, []

def get_league_data():
    standings, _ = get_dashboard_data()
    return standings