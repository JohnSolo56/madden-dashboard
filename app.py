from flask import Flask, render_template
from scraper import get_dashboard_data

app = Flask(__name__)

@app.route("/")
def home():
    standings, schedule = get_dashboard_data()

    afc = standings[standings["Conference"] == "AFC"].sort_values("Seed")
    nfc = standings[standings["Conference"] == "NFC"].sort_values("Seed")

    return render_template(
        "index.html",
        afc=afc.to_dict("records"),
        nfc=nfc.to_dict("records")
    )

@app.route("/schedule")
def schedule():
    standings, schedule_rows = get_dashboard_data()

    return render_template(
        "schedule.html",
        schedule=schedule_rows
    )

if __name__ == "__main__":
    app.run(debug=True)