from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import os
import re

STANDINGS_URL = "https://neonsportz.com/leagues/JD/standings"

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
    options = Options()

    chrome_bin = os.environ.get("CHROME_BIN")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")

    if chrome_bin:
        options.binary_location = chrome_bin

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1920,1080")

    if chromedriver_path:
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

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

        teams.append({
            "Conference": get_conference(team),
            "Division": DIVISIONS[team],
            "Team": team,
            "Wins": int(cols[1]),
            "Losses": int(cols[2]),
            "Ties": int(cols[3]),
            "Record": f"{cols[1]}-{cols[2]}",
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
            "Remaining": 0,
            "RemainingGames": "Coming Soon",
            "AvgDifficulty": 0
        })

    return pd.DataFrame(teams)

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

def get_dashboard_data():
    driver, wait = create_driver()

    standings = scrape_standings(driver, wait)

    driver.quit()

    standings = apply_nfl_seeding(standings)
    standings = add_status_and_magic_numbers(standings)

    return standings, []

def get_league_data():
    standings, _ = get_dashboard_data()
    return standings