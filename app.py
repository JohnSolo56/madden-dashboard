from flask import Flask, render_template, request
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