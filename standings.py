import pandas as pd
import requests
from datetime import datetime, timezone
import time
import os
import shutil


STANDINGS_URL = "https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings"
SCHEDULE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"

def _fetch_json(url: str) -> dict:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _stat(entry: dict, name: str):
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            return stat.get("value")
    return None


def get_standings():
    data = _fetch_json(STANDINGS_URL)
    teams = []
    for child in data.get("children", []):
        conference = child.get("name")
        for entry in child.get("standings", {}).get("entries", []):
            team_info = entry.get("team", {})
            team_id = team_info.get("id")
            name = team_info.get("displayName")
            wins = _stat(entry, "wins") or 0
            losses = _stat(entry, "losses") or 0
            win_pct = _stat(entry, "winPercent") or 0
            teams.append({
                "id": str(team_id),
                "team": name,
                "wins": int(wins),
                "losses": int(losses),
                "win_pct": float(win_pct),
                "conference": conference,
            })
    return teams


def get_team_results(team_id: str):
    url = SCHEDULE_URL.format(team_id=team_id)
    try:
        data = _fetch_json(url)
    except requests.HTTPError:
        return []
    opponents_beaten = []

    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        me = next((c for c in competitors if c.get("id") == str(team_id)), None)
        opp = next((c for c in competitors if c.get("id") != str(team_id)), None)
        if not me or not opp:
            continue
        if me.get("winner"):
            opp_name = opp.get("displayName") or opp.get("team", {}).get("displayName")
            opponents_beaten.append(opp_name)

    return opponents_beaten


def build_dataset():
    standings = get_standings()

    # top 7 per conference = playoff picture
    playoff_teams = set()
    for conf in {t["conference"] for t in standings if t.get("conference")}:
        conf_teams = [t for t in standings if t.get("conference") == conf]
        conf_teams.sort(key=lambda t: (-t["wins"], t["losses"], -t["win_pct"]))
        playoff_teams.update(t["team"] for t in conf_teams[:7])

    dataset = []
    
    # Pre-fetch all schedule data
    all_schedules = {}
    for team in standings:
        all_schedules[team["id"]] = get_team_results(team["id"])

    for team in standings:
        beaten = all_schedules[team["id"]]
        team["opponents_beaten"] = beaten
        playoff_beaten = [opp for opp in beaten if opp in playoff_teams]
        team["playoff_opponents_beaten"] = playoff_beaten
        team["playoff_beaten_count"] = len(playoff_beaten)
        
        # Count unique playoff teams played against (both wins and losses)
        playoff_played = set()
        
        # Add playoff teams this team beat
        for opp in beaten:
            if opp in playoff_teams:
                playoff_played.add(opp)
        
        # Add playoff teams that beat this team
        for other_team in standings:
            if other_team["team"] in playoff_teams:
                other_beaten = all_schedules[other_team["id"]]
                if team["team"] in other_beaten:
                    playoff_played.add(other_team["team"])
        
        team["playoff_teams_played"] = len(playoff_played)
        team["in_playoffs"] = team["team"] in playoff_teams
        dataset.append(team)

    return pd.DataFrame(dataset)

if __name__ == "__main__":
    df = build_dataset()
    playoff_sorted = df[df["in_playoffs"]].sort_values(
        by=["playoff_beaten_count", "wins", "win_pct"], ascending=[False, False, False]
    )
    non_playoff_sorted = df[~df["in_playoffs"]].sort_values(
        by=["playoff_beaten_count", "wins", "win_pct"], ascending=[False, False, False]
    )

    print("=== Playoff teams ===")
    print(playoff_sorted)
    print("\n=== Non-playoff teams ===")
    print(non_playoff_sorted)

    combined = pd.concat([playoff_sorted, non_playoff_sorted], ignore_index=True)
    combined.to_csv("nfl_team_records.csv", index=False)

    # Write an HTML report with both tables.
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>NFL Teams & Playoff Wins</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        h1, h2 {{ margin-bottom: 8px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; }}
        th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
        th {{ background: #f2f2f2; font-weight: bold; }}
        .updated {{ color: #555; margin: 0 0 16px 0; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <h1>NFL Teams & Playoff Picture</h1>
    <p class=\"updated\">Last updated: {updated_at}</p>
    <h2>Playoff Teams</h2>
    {playoff_table}
    <h2>Non-Playoff Teams</h2>
    {non_table}
</body>
</html>
""".format(
        updated_at=updated_at,
    playoff_table=playoff_sorted.to_html(index=False, border=0, justify="left"),
        non_table=non_playoff_sorted.to_html(index=False, border=0, justify="left"),
    )

    with open("nfl_team_records.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Move CSV and HTML to OUTPUT_DIR only if DOCKER environment is set
    is_docker = os.environ.get("DOCKER", "").lower() in ("true", "1", "yes")
    output_dir = os.environ.get("OUTPUT_DIR")
    
    if is_docker and output_dir:
        try:
            os.makedirs(output_dir, exist_ok=True)
            # Move CSV
            src_csv = os.path.abspath("nfl_team_records.csv")
            dst_csv = os.path.join(output_dir, "nfl_team_records.csv")
            if os.path.exists(dst_csv):
                os.remove(dst_csv)
            shutil.move(src_csv, dst_csv)
            # Move HTML
            src_html = os.path.abspath("nfl_team_records.html")
            dst_html = os.path.join(output_dir, "nfl_team_records.html")
            if os.path.exists(dst_html):
                os.remove(dst_html)
            shutil.move(src_html, dst_html)
            print(f"Reports moved to: {output_dir}")
        except Exception as e:
            print(f"Warning: failed to move files to OUTPUT_DIR: {e}")
    else:
        print("Reports generated locally: nfl_team_records.csv, nfl_team_records.html")
    
    # Sleep for 8 hours before ending the script, comment this line out if you want to run the script on demand
    if is_docker:
        print("Sleeping for 8 hours...")
        time.sleep(8*60*60)
