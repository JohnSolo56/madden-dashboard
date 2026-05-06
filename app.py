from flask import Flask, render_template, redirect, url_for
from scraper import get_dashboard_data, get_fallback_dashboard_data

app = Flask(__name__)

CACHED_STANDINGS = None
CACHED_SCHEDULE = []
LAST_ERROR = None

@app.route("/")
def home():
    global CACHED_STANDINGS, CACHED_SCHEDULE, LAST_ERROR

    if CACHED_STANDINGS is None:
        CACHED_STANDINGS, CACHED_SCHEDULE = get_fallback_dashboard_data()
        LAST_ERROR = "Live data has not been refreshed yet."

    afc = CACHED_STANDINGS[CACHED_STANDINGS["Conference"] == "AFC"].sort_values("Seed")
    nfc = CACHED_STANDINGS[CACHED_STANDINGS["Conference"] == "NFC"].sort_values("Seed")

    return render_template(
        "index.html",
        afc=afc.to_dict("records"),
        nfc=nfc.to_dict("records"),
        last_error=LAST_ERROR
    )

@app.route("/refresh")
def refresh():
    global CACHED_STANDINGS, CACHED_SCHEDULE, LAST_ERROR

    try:
        CACHED_STANDINGS, CACHED_SCHEDULE = get_dashboard_data()
        LAST_ERROR = None
    except Exception as e:
        if CACHED_STANDINGS is None:
            CACHED_STANDINGS, CACHED_SCHEDULE = get_fallback_dashboard_data()
        LAST_ERROR = str(e)

    return redirect(url_for("home"))

@app.route("/schedule")
def schedule():
    global CACHED_STANDINGS, CACHED_SCHEDULE, LAST_ERROR

    if CACHED_STANDINGS is None:
        CACHED_STANDINGS, CACHED_SCHEDULE = get_fallback_dashboard_data()
        LAST_ERROR = "Live data has not been refreshed yet."

    return render_template(
        "schedule.html",
        schedule=CACHED_SCHEDULE,
        last_error=LAST_ERROR
    )

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)