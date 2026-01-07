import pandas as pd
import requests
from datetime import datetime, timezone
import time
import os
import shutil
import json


STANDINGS_URL = "https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings"
SCHEDULE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"

# NFL Divisions
DIVISIONS = {
    # AFC
    "AFC East": {"conference": "American Football Conference", "teams": ["Buffalo Bills", "New England Patriots", "New York Jets", "Miami Dolphins"]},
    "AFC North": {"conference": "American Football Conference", "teams": ["Baltimore Ravens", "Pittsburgh Steelers", "Cincinnati Bengals", "Cleveland Browns"]},
    "AFC South": {"conference": "American Football Conference", "teams": ["Houston Texans", "Indianapolis Colts", "Tennessee Titans", "Jacksonville Jaguars"]},
    "AFC West": {"conference": "American Football Conference", "teams": ["Kansas City Chiefs", "Los Angeles Chargers", "Denver Broncos", "Las Vegas Raiders"]},
    # NFC
    "NFC East": {"conference": "National Football Conference", "teams": ["Dallas Cowboys", "Philadelphia Eagles", "Washington Commanders", "New York Giants"]},
    "NFC North": {"conference": "National Football Conference", "teams": ["Chicago Bears", "Green Bay Packers", "Minnesota Vikings", "Detroit Lions"]},
    "NFC South": {"conference": "National Football Conference", "teams": ["Atlanta Falcons", "Carolina Panthers", "New Orleans Saints", "Tampa Bay Buccaneers"]},
    "NFC West": {"conference": "National Football Conference", "teams": ["Los Angeles Rams", "San Francisco 49ers", "Seattle Seahawks", "Arizona Cardinals"]},
}

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
            point_diff = _stat(entry, "pointDifferential") or 0
            div_wins = _stat(entry, "divisionWins") or 0
            div_losses = _stat(entry, "divisionLosses") or 0
            points_for = _stat(entry, "pointsFor") or 0
            points_against = _stat(entry, "pointsAgainst") or 0
            espn_playoff_seed = _stat(entry, "playoffSeed") or None
            
            # Try to get conference record (may be nested under vs. Conf.)
            conf_record = None
            for stat in entry.get("stats", []):
                if stat.get("name") == "vs. Conf.":
                    conf_record = stat.get("value")
                    break
            
            teams.append({
                "id": str(team_id),
                "team": name,
                "wins": int(wins),
                "losses": int(losses),
                "win_pct": float(win_pct),
                "point_diff": float(point_diff),
                "div_wins": int(div_wins),
                "div_losses": int(div_losses),
                "points_for": int(points_for),
                "points_against": int(points_against),
                "espn_playoff_seed": int(espn_playoff_seed) if espn_playoff_seed else None,
                "conf_record": conf_record,
                "conference": conference,
            })
    return teams


def get_team_results(team_id: str):
    url = SCHEDULE_URL.format(team_id=team_id)
    try:
        data = _fetch_json(url)
    except requests.HTTPError:
        return [], {}, []
    opponents_beaten = []
    h2h_records = {}  # opponent_name -> {"wins": int, "losses": int}
    all_opponents = []  # All opponents played (for strength of schedule)

    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        me = next((c for c in competitors if c.get("id") == str(team_id)), None)
        opp = next((c for c in competitors if c.get("id") != str(team_id)), None)
        if not me or not opp:
            continue
        
        opp_name = opp.get("displayName") or opp.get("team", {}).get("displayName")
        all_opponents.append(opp_name)
        
        if me.get("winner"):
            opponents_beaten.append(opp_name)
        
        # Track head-to-head records against all opponents
        if opp_name not in h2h_records:
            h2h_records[opp_name] = {"wins": 0, "losses": 0}
        if me.get("winner"):
            h2h_records[opp_name]["wins"] += 1
        else:
            h2h_records[opp_name]["losses"] += 1

    return opponents_beaten, h2h_records, all_opponents


def compute_tiebreaker_key(team: dict, tied_teams: list, all_schedules: dict) -> tuple:
    """
    Compute NFL tiebreaker key for sorting teams with identical records.
    Returns a tuple that can be used as a sort key.
    
    Tiebreaker order (NFL rules):
    1. Head-to-head win-loss record among tied teams
    2. Division win-loss record
    3. Common games win-loss record  
    4. Conference win-loss record (approx via overall record)
    5. Strength of victory
    6. Strength of schedule
    7. Points scored vs allowed
    8. Point differential in common games
    9. Point differential overall
    10. Net touchdowns (not available, use point_diff as proxy)
    """
    
    tied_team_names = {t["team"] for t in tied_teams}
    
    # Tiebreaker 1: Head-to-head record among tied teams
    h2h_record = all_schedules.get(team["id"], ({}, {}))[1]  # Get h2h_records from tuple
    h2h_wins = sum(h2h_record.get(opp, {}).get("wins", 0) for opp in tied_team_names if opp != team["team"])
    h2h_losses = sum(h2h_record.get(opp, {}).get("losses", 0) for opp in tied_team_names if opp != team["team"])
    h2h_pct = h2h_wins / (h2h_wins + h2h_losses) if (h2h_wins + h2h_losses) > 0 else 0
    
    # Tiebreaker 2: Division record
    div_pct = team["div_wins"] / (team["div_wins"] + team["div_losses"]) if (team["div_wins"] + team["div_losses"]) > 0 else 0
    
    # Tiebreaker 9: Point differential (as primary tiebreaker when others are equal)
    point_diff = team["point_diff"]
    
    # Return tuple for sorting: higher h2h%, higher div%, higher point_diff
    return (-h2h_pct, -div_pct, -point_diff)


def apply_nfl_tiebreaker(teams: list, all_schedules: dict) -> list:
    """
    Apply NFL tiebreaker rules recursively to break ties among teams with same record.
    This implements the official NFL tiebreaker procedure where:
    - If team A beats team B head-to-head, A ranks higher
    - When tied teams play each other, eliminate teams they collectively beat
    - Continue with remaining teams using next tiebreaker
    """
    
    if len(teams) <= 1:
        return teams
    
    # Tiebreaker 1: Head-to-head among all tied teams
    tied_names = {t["team"] for t in teams}
    h2h_records = {}
    
    for team in teams:
        h2h_record = all_schedules.get(team["id"], ({}, {}))[1]
        h2h_wins = sum(h2h_record.get(opp, {}).get("wins", 0) for opp in tied_names if opp != team["team"])
        h2h_losses = sum(h2h_record.get(opp, {}).get("losses", 0) for opp in tied_names if opp != team["team"])
        h2h_pct = h2h_wins / (h2h_wins + h2h_losses) if (h2h_wins + h2h_losses) > 0 else 0
        h2h_records[team["team"]] = h2h_pct
    
    # Group teams by their H2H percentage
    from collections import defaultdict
    by_h2h = defaultdict(list)
    for team in teams:
        by_h2h[h2h_records[team["team"]]].append(team)
    
    # If head-to-head clearly separates teams, use that
    sorted_teams = []
    for h2h_pct in sorted(by_h2h.keys(), reverse=True):
        group = by_h2h[h2h_pct]
        if len(group) > 1:
            # Recursively apply next tiebreaker (division record)
            sorted_group = apply_div_tiebreaker(group, all_schedules)
            sorted_teams.extend(sorted_group)
        else:
            sorted_teams.extend(group)
    
    return sorted_teams


def apply_div_tiebreaker(teams: list, all_schedules: dict) -> list:
    """Apply division record as tiebreaker."""
    if len(teams) <= 1:
        return teams
    
    # Tiebreaker 2: Division record
    teams_sorted = sorted(teams, key=lambda t: (
        -(t["div_wins"] / (t["div_wins"] + t["div_losses"]) if (t["div_wins"] + t["div_losses"]) > 0 else 0),
        -(t["point_diff"])  # Point differential as sub-tiebreaker
    ))
    
    # Group teams with same division record
    from collections import defaultdict
    by_div_pct = defaultdict(list)
    for team in teams_sorted:
        div_pct = team["div_wins"] / (team["div_wins"] + team["div_losses"]) if (team["div_wins"] + team["div_losses"]) > 0 else 0
        by_div_pct[div_pct].append(team)
    
    # If division record clearly separates, use that
    result = []
    for div_pct in sorted(by_div_pct.keys(), reverse=True):
        group = by_div_pct[div_pct]
        if len(group) > 1:
            # Fall through to point differential
            group.sort(key=lambda t: -t["point_diff"])
            result.extend(group)
        else:
            result.extend(group)
    
    return result


def build_dataset():
    standings = get_standings()

    # Pre-fetch all schedule data
    all_schedules = {}
    for team in standings:
        result = get_team_results(team["id"])
        all_schedules[team["id"]] = result

    # Map team name -> win_pct for computing wins against teams with winning records
    win_pct_map = {t["team"]: t["win_pct"] for t in standings}
    
    # Use ESPN's official playoff seed for all teams
    # Identify playoff teams as those with seed 1-7 (actual playoff teams)
    playoff_teams = {t["team"]: t["espn_playoff_seed"] for t in standings if t["espn_playoff_seed"] is not None and t["espn_playoff_seed"] <= 7}

    dataset = []
    
    for team in standings:
        beaten, h2h_records, all_opponents = all_schedules[team["id"]]
        
        # Calculate strength of schedule (average win percentage of all opponents)
        if all_opponents:
            sos = sum(win_pct_map.get(opp, 0) for opp in all_opponents) / len(all_opponents)
        else:
            sos = 0.0
        team["sos"] = round(sos, 3)
        
        # Format opponents_beaten with duplicate counts
        from collections import Counter
        beaten_counts = Counter(beaten)
        opponents_beaten_formatted = [f"{opp} (x{count})" if count > 1 else opp for opp, count in beaten_counts.items()]
        team["opponents_beaten"] = opponents_beaten_formatted
        
        # Get playoff opponents beaten
        playoff_beaten = [opp for opp in beaten if opp in playoff_teams]
        playoff_beaten_counts = Counter(playoff_beaten)
        playoff_opponents_beaten_formatted = [f"{opp} (x{count})" if count > 1 else opp for opp, count in playoff_beaten_counts.items()]
        team["playoff_opponents_beaten"] = playoff_opponents_beaten_formatted
        
        # Count unique playoff teams beaten and total wins against them
        unique_playoff_beaten = len(set(playoff_beaten))
        total_playoff_beaten = len(playoff_beaten)
        duplicate_wins = total_playoff_beaten - unique_playoff_beaten
        
        team["playoff_beaten_count"] = f"{unique_playoff_beaten} ({duplicate_wins})" if duplicate_wins > 0 else str(unique_playoff_beaten)
        
        # Count unique playoff teams played against (both wins and losses)
        playoff_played = set()
        playoff_games_count = 0  # Total games against playoff teams
        
        # Add playoff teams this team beat
        for opp in beaten:
            if opp in playoff_teams:
                playoff_played.add(opp)
                playoff_games_count += 1
        
        # Add playoff teams that beat this team
        for other_team in standings:
            if other_team["team"] in playoff_teams:
                other_beaten, _, _ = all_schedules[other_team["id"]]
                if team["team"] in other_beaten:
                    playoff_played.add(other_team["team"])
                    playoff_games_count += 1
        
        unique_playoff_teams = len(playoff_played)
        duplicate_games = playoff_games_count - unique_playoff_teams
        
        team["playoff_teams_played"] = f"{unique_playoff_teams} ({duplicate_games})" if duplicate_games > 0 else str(unique_playoff_teams)
        team["in_playoffs"] = team["team"] in playoff_teams
        
        # Add seed from ESPN for all teams
        team["seed"] = team["espn_playoff_seed"]

        # Wins against teams with a winning record (> .500)
        total_wins_vs_winning = sum(1 for opp in beaten if win_pct_map.get(opp, 0) > 0.5)
        beaten_winning = [opp for opp, count in beaten_counts.items() if win_pct_map.get(opp, 0) > 0.5]
        beaten_winning_formatted = [f"{opp} (x{beaten_counts[opp]})" if beaten_counts[opp] > 1 else opp for opp in beaten_winning]
        # Show unique wins with duplicate count in parentheses (e.g., "3 (1)")
        unique_wins_vs_winning = len(beaten_winning)
        duplicate_wins_vs_winning = total_wins_vs_winning - unique_wins_vs_winning
        team["wins_vs_winning"] = f"{unique_wins_vs_winning} ({duplicate_wins_vs_winning})" if duplicate_wins_vs_winning > 0 else str(unique_wins_vs_winning)
        team["opponents_beaten_vs_winning"] = beaten_winning_formatted

        # Winning teams played (unique count, with duplicate games in parentheses)
        winning_played = set()
        winning_games_count = 0

        # Teams this team beat that have winning records
        for opp in beaten:
            if win_pct_map.get(opp, 0) > 0.5:
                winning_played.add(opp)
                winning_games_count += 1

        # Teams that beat this team and have winning records
        for other_team in standings:
            other_name = other_team["team"]
            other_win_pct = other_team.get("win_pct", 0)
            if other_win_pct <= 0.5:
                continue
            other_beaten, _, _ = all_schedules[other_team["id"]]
            if team["team"] in other_beaten:
                winning_played.add(other_name)
                winning_games_count += 1

        unique_winning_teams = len(winning_played)
        duplicate_winning = winning_games_count - unique_winning_teams
        team["winning_teams_played"] = f"{unique_winning_teams} ({duplicate_winning})" if duplicate_winning > 0 else str(unique_winning_teams)
        
        # Calculate quality score: (Win_Pct × 40) + (SOS × 20) + (Wins_vs_Winning × 2.5) + (Playoff_Wins × 4)
        quality_score = (team["win_pct"] * 40) + (team["sos"] * 20) + (total_wins_vs_winning * 2.5) + (total_playoff_beaten * 4)
        team["quality_score"] = round(quality_score, 2)
        
        dataset.append(team)

    return pd.DataFrame(dataset)

if __name__ == "__main__":
    import sys
    
    df = build_dataset()
    
    # Filter to only playoff teams (seeds 1-7 per conference based on ESPN data)
    # ESPN playoff seed tells us if they're in the playoffs
    playoff_df = df[df["in_playoffs"]].copy()
    non_playoff_df = df[~df["in_playoffs"]].copy()
    
    # Remove ID column from both
    cols_to_drop = ["id"]
    playoff_df = playoff_df.drop(columns=cols_to_drop)
    non_playoff_df = non_playoff_df.drop(columns=cols_to_drop)
    
    # Sort both by seed
    playoff_df = playoff_df.sort_values(by="seed", ascending=True)
    non_playoff_df = non_playoff_df.sort_values(by="seed", ascending=True)

    # Columns to display
    playoff_display_cols = ["team", "seed", "conference", "wins", "losses", "win_pct", "sos", "quality_score", "wins_vs_winning", "winning_teams_played", "opponents_beaten_vs_winning",  "playoff_beaten_count", "playoff_teams_played", "opponents_beaten", "playoff_opponents_beaten"]
    non_playoff_display_cols = ["team", "seed", "conference", "wins", "losses", "win_pct", "sos", "quality_score", "wins_vs_winning", "winning_teams_played", "opponents_beaten_vs_winning",  "playoff_beaten_count", "playoff_teams_played", "opponents_beaten", "playoff_opponents_beaten"]
    
    # Convert seed to int for display
    playoff_df_display = playoff_df[playoff_display_cols].copy()
    playoff_df_display["seed"] = playoff_df_display["seed"].astype("Int64")
    playoff_df_display = playoff_df_display.rename(columns={
        "playoff_beaten_count": "playoff_beaten (dups)",
        "playoff_teams_played": "playoff_teams_played (dups)",
        "wins_vs_winning": "wins_vs_winning (dups)",
        "opponents_beaten_vs_winning": "opponents_beaten_vs_winning (dups)"
    })
    
    non_playoff_df_display = non_playoff_df[non_playoff_display_cols].copy()
    non_playoff_df_display["seed"] = non_playoff_df_display["seed"].astype("Int64")
    non_playoff_df_display = non_playoff_df_display.rename(columns={
        "playoff_beaten_count": "playoff_beaten (dups)",
        "playoff_teams_played": "playoff_teams_played (dups)",
        "wins_vs_winning": "wins_vs_winning (dups)",
        "opponents_beaten_vs_winning": "opponents_beaten_vs_winning (dups)"
    })
    
    print("=== Playoff teams ===")
    print(playoff_df_display.to_string(index=False))
    print("\n=== Non-playoff teams ===")
    print(non_playoff_df_display.to_string(index=False))

    # Save full dataframes to CSV (with all columns)
    combined = pd.concat([playoff_df, non_playoff_df], ignore_index=True)
    # Determine write directory (use OUTPUT_DIR when running in Docker)
    is_docker = os.environ.get("DOCKER", "").lower() in ("true", "1", "yes")
    output_dir = os.environ.get("OUTPUT_DIR")
    write_dir = output_dir if (is_docker and output_dir) else os.path.abspath(".")
    os.makedirs(write_dir, exist_ok=True)

    # Save CSV to write_dir
    combined_path = os.path.join(write_dir, "nfl_team_records.csv")
    combined.to_csv(combined_path, index=False)

    # Also write JSON output for consumption by external programs (COBOL, etc.)
    combined_records = combined.where(pd.notnull(combined), None).to_dict(orient="records")
    with open(os.path.join(write_dir, "nfl_team_records.json"), "w", encoding="utf-8") as jf:
        json.dump(combined_records, jf, ensure_ascii=False, indent=2)

    # Write separate JSON files for playoff and non-playoff sections (display columns)
    playoff_records = playoff_df[playoff_display_cols].where(pd.notnull(playoff_df[playoff_display_cols]), None).to_dict(orient="records")
    non_playoff_records = non_playoff_df[non_playoff_display_cols].where(pd.notnull(non_playoff_df[non_playoff_display_cols]), None).to_dict(orient="records")
    with open(os.path.join(write_dir, "playoff_team_records.json"), "w", encoding="utf-8") as pf:
        json.dump(playoff_records, pf, ensure_ascii=False, indent=2)
    with open(os.path.join(write_dir, "non_playoff_team_records.json"), "w", encoding="utf-8") as nf:
        json.dump(non_playoff_records, nf, ensure_ascii=False, indent=2)

    # Write an HTML report with display columns only
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    # Convert seed to int for HTML
    playoff_df_html = playoff_df[playoff_display_cols].copy()
    playoff_df_html["seed"] = playoff_df_html["seed"].astype("Int64")
    playoff_df_html = playoff_df_html.rename(columns={
        "playoff_beaten_count": "playoff_beaten (dups)",
        "playoff_teams_played": "playoff_teams_played (dups)",
        "wins_vs_winning": "wins_vs_winning (dups)",
        "opponents_beaten_vs_winning": "opponents_beaten_vs_winning (dups)"
    })
    
    non_playoff_df_html = non_playoff_df[non_playoff_display_cols].copy()
    non_playoff_df_html["seed"] = non_playoff_df_html["seed"].astype("Int64")
    non_playoff_df_html = non_playoff_df_html.rename(columns={
        "playoff_beaten_count": "playoff_beaten (dups)",
        "playoff_teams_played": "playoff_teams_played (dups)",
        "wins_vs_winning": "wins_vs_winning (dups)",
        "opponents_beaten_vs_winning": "opponents_beaten_vs_winning (dups)"
    })
    
    # Build sortable HTML tables
    def build_sortable_table(df, table_id):
        html_parts = [f'<table id="{table_id}">']
        html_parts.append('<thead><tr>')
        for idx, col in enumerate(df.columns):
            html_parts.append(f'<th onclick="sortTable(\'{table_id}\', {idx})">{col}</th>')
        html_parts.append('</tr></thead><tbody>')
        
        for _, row in df.iterrows():
            html_parts.append('<tr>')
            for val in row:
                html_parts.append(f'<td>{val}</td>')
            html_parts.append('</tr>')
        
        html_parts.append('</tbody></table>')
        return ''.join(html_parts)
    
    playoff_table_html = build_sortable_table(playoff_df_html, "playoff-table")
    non_playoff_table_html = build_sortable_table(non_playoff_df_html, "non-playoff-table")
    
    html = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>NFL Teams & Playoff Picture</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        h1, h2 {{ margin-bottom: 8px; }}
        .nav {{ margin-bottom: 16px; }}
        .nav a {{ margin-right: 16px; padding: 8px 12px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }}
        .nav a:hover {{ background: #0056b3; }}
        .explanation {{ background: #e8f4f8; padding: 12px 16px; border-left: 4px solid #007bff; margin-bottom: 20px; border-radius: 4px; }}
        .explanation h3 {{ margin-top: 0; color: #007bff; }}
        .explanation p {{ margin: 6px 0; font-size: 0.9rem; }}
        .explanation ul {{ margin: 6px 0; padding-left: 20px; font-size: 0.9rem; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; }}
        th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
        th {{ background: #f2f2f2; font-weight: bold; cursor: pointer; user-select: none; }}
        th:hover {{ background: #e0e0e0; }}
        th.sort-asc::after {{ content: ' ▲'; }}
        th.sort-desc::after {{ content: ' ▼'; }}
        .updated {{ color: #555; margin: 0 0 16px 0; font-size: 0.9rem; }}
    </style>
    <script>
        function sortTable(tableId, columnIndex) {{
            const table = document.getElementById(tableId);
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const headers = table.querySelectorAll('th');
            const currentHeader = headers[columnIndex];
            
            // Determine sort direction
            let sortDir = 'asc';
            if (currentHeader.classList.contains('sort-asc')) {{
                sortDir = 'desc';
            }}
            
            // Remove all sort classes
            headers.forEach(h => {{
                h.classList.remove('sort-asc', 'sort-desc');
            }});
            
            // Add sort class to current header
            currentHeader.classList.add('sort-' + sortDir);
            
            // Sort rows
            rows.sort((a, b) => {{
                const aCell = a.cells[columnIndex].textContent.trim();
                const bCell = b.cells[columnIndex].textContent.trim();
                
                // Try to parse as number
                const aNum = parseFloat(aCell);
                const bNum = parseFloat(bCell);
                
                let comparison = 0;
                if (!isNaN(aNum) && !isNaN(bNum)) {{
                    comparison = aNum - bNum;
                }} else {{
                    comparison = aCell.localeCompare(bCell);
                }}
                
                return sortDir === 'asc' ? comparison : -comparison;
            }});
            
            // Reorder rows
            rows.forEach(row => tbody.appendChild(row));
        }}
    </script>
</head>
<body>
    <h1>NFL Teams & Playoff Picture</h1>
    <div class=\"nav\">
        <a href=\"nfl_all_teams.html\">View All Teams by Quality Score</a>
    </div>
    <p class=\"updated\">Last updated: {updated_at}</p>
    
    <div class=\"explanation\">
        <h3>About Quality Score</h3>
        <p><strong>Quality Score</strong> is a composite metric that ranks teams based on four key performance factors:</p>
        <ul>
            <li><strong>Win % (40% weight):</strong> Overall winning percentage—the foundation of team success</li>
            <li><strong>Strength of Schedule (20% weight):</strong> Average win percentage of all opponents faced—rewards teams who played tougher competition</li>
            <li><strong>Wins vs Winning Teams (2.5 pts each):</strong> Quality wins against teams with winning records (>50% win %)</li>
            <li><strong>Playoff Wins (4 pts each):</strong> Victories against current playoff-contending teams—most prestigious wins</li>
        </ul>
        <p><strong>Formula:</strong> (Win % × 40) + (SOS × 20) + (Wins vs Winning × 2.5) + (Playoff Wins × 4)</p>
        <p>Higher scores indicate stronger overall team quality considering both results and strength of opposition.</p>
    </div>
    
    <h2>Playoff Teams</h2>
    {playoff_table}
    <h2>Non-Playoff Teams</h2>
    {non_table}
</body>
</html>
""".format(
        updated_at=updated_at,
        playoff_table=playoff_table_html,
        non_table=non_playoff_table_html,
    )

    with open("nfl_team_records.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Generate a separate HTML file with all teams combined (sorted by quality score)
    all_teams_df = combined[playoff_display_cols].copy()
    all_teams_df = all_teams_df.sort_values(by="quality_score", ascending=False).reset_index(drop=True)
    all_teams_df["seed"] = all_teams_df["seed"].astype("Int64")
    all_teams_df = all_teams_df.rename(columns={
        "playoff_beaten_count": "playoff_beaten (dups)",
        "playoff_teams_played": "playoff_teams_played (dups)",
        "wins_vs_winning": "wins_vs_winning (dups)",
        "opponents_beaten_vs_winning": "opponents_beaten_vs_winning (dups)"
    })
    
    all_teams_table_html = build_sortable_table(all_teams_df, "all-teams-table")
    
    all_teams_html = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>NFL Teams - All Teams by Quality Score</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        h1 {{ margin-bottom: 8px; }}
        .nav {{ margin-bottom: 16px; }}
        .nav a {{ margin-right: 16px; padding: 8px 12px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }}
        .nav a:hover {{ background: #0056b3; }}
        .explanation {{ background: #e8f4f8; padding: 12px 16px; border-left: 4px solid #007bff; margin-bottom: 20px; border-radius: 4px; }}
        .explanation h3 {{ margin-top: 0; color: #007bff; }}
        .explanation p {{ margin: 6px 0; font-size: 0.9rem; }}
        .explanation ul {{ margin: 6px 0; padding-left: 20px; font-size: 0.9rem; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; }}
        th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
        th {{ background: #f2f2f2; font-weight: bold; cursor: pointer; user-select: none; }}
        th:hover {{ background: #e0e0e0; }}
        th.sort-asc::after {{ content: ' ▲'; }}
        th.sort-desc::after {{ content: ' ▼'; }}
        .updated {{ color: #555; margin: 0 0 16px 0; font-size: 0.9rem; }}
    </style>
    <script>
        function sortTable(tableId, columnIndex) {{
            const table = document.getElementById(tableId);
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const headers = table.querySelectorAll('th');
            const currentHeader = headers[columnIndex];
            
            // Determine sort direction
            let sortDir = 'asc';
            if (currentHeader.classList.contains('sort-asc')) {{
                sortDir = 'desc';
            }}
            
            // Remove all sort classes
            headers.forEach(h => {{
                h.classList.remove('sort-asc', 'sort-desc');
            }});
            
            // Add sort class to current header
            currentHeader.classList.add('sort-' + sortDir);
            
            // Sort rows
            rows.sort((a, b) => {{
                const aCell = a.cells[columnIndex].textContent.trim();
                const bCell = b.cells[columnIndex].textContent.trim();
                
                // Try to parse as number
                const aNum = parseFloat(aCell);
                const bNum = parseFloat(bCell);
                
                let comparison = 0;
                if (!isNaN(aNum) && !isNaN(bNum)) {{
                    comparison = aNum - bNum;
                }} else {{
                    comparison = aCell.localeCompare(bCell);
                }}
                
                return sortDir === 'asc' ? comparison : -comparison;
            }});
            
            // Reorder rows
            rows.forEach(row => tbody.appendChild(row));
        }}
    </script>
</head>
<body>
    <h1>NFL Teams - All Teams with Quality Score</h1>
    <div class=\"nav\">
        <a href=\"nfl_team_records.html\">View Playoff/Non-Playoff Split</a>
    </div>
    <p class=\"updated\">Last updated: {updated_at}</p>
    
    <div class=\"explanation\">
        <h3>About Quality Score</h3>
        <p><strong>Quality Score</strong> is a composite metric that ranks teams based on four key performance factors:</p>
        <ul>
            <li><strong>Win % (40% weight):</strong> Overall winning percentage—the foundation of team success</li>
            <li><strong>Strength of Schedule (20% weight):</strong> Average win percentage of all opponents faced—rewards teams who played tougher competition</li>
            <li><strong>Wins vs Winning Teams (2.5 pts each):</strong> Quality wins against teams with winning records (>50% win %)</li>
            <li><strong>Playoff Wins (4 pts each):</strong> Victories against current playoff-contending teams—most prestigious wins</li>
        </ul>
        <p><strong>Formula:</strong> (Win % × 40) + (SOS × 20) + (Wins vs Winning × 2.5) + (Playoff Wins × 4)</p>
        <p>Higher scores indicate stronger overall team quality considering both results and strength of opposition.</p>
    </div>
    
    {all_teams_table}
</body>
</html>
""".format(
        updated_at=updated_at,
        all_teams_table=all_teams_table_html,
    )

    with open("nfl_all_teams.html", "w", encoding="utf-8") as f:
        f.write(all_teams_html)

    # Move CSV and HTML to OUTPUT_DIR only if DOCKER environment is set
    is_docker = os.environ.get("DOCKER", "").lower() in ("true", "1", "yes")
    output_dir = os.environ.get("OUTPUT_DIR")
    
    if is_docker and output_dir:
        try:
            os.makedirs(output_dir, exist_ok=True)
            # Move CSV
            src_csv = os.path.abspath("nfl_team_records.csv")
            dst_csv = os.path.join(output_dir, "nfl_team_records.csv")
            if os.path.exists(src_csv):
                if os.path.exists(dst_csv):
                    os.remove(dst_csv)
                shutil.move(src_csv, dst_csv)
            # Move HTML
            src_html = os.path.abspath("nfl_team_records.html")
            dst_html = os.path.join(output_dir, "nfl_team_records.html")
            if os.path.exists(src_html):
                if os.path.exists(dst_html):
                    os.remove(dst_html)
                shutil.move(src_html, dst_html)
            # Move all-teams HTML
            src_all = os.path.abspath("nfl_all_teams.html")
            dst_all = os.path.join(output_dir, "nfl_all_teams.html")
            if os.path.exists(src_all):
                if os.path.exists(dst_all):
                    os.remove(dst_all)
                shutil.move(src_all, dst_all)
            # Move JSON outputs as well
            try:
                src_json = os.path.abspath("nfl_team_records.json")
                dst_json = os.path.join(output_dir, "nfl_team_records.json")
                if os.path.exists(src_json):
                    if os.path.exists(dst_json):
                        os.remove(dst_json)
                    shutil.move(src_json, dst_json)

                src_pf = os.path.abspath("playoff_team_records.json")
                dst_pf = os.path.join(output_dir, "playoff_team_records.json")
                if os.path.exists(src_pf):
                    if os.path.exists(dst_pf):
                        os.remove(dst_pf)
                    shutil.move(src_pf, dst_pf)

                src_nf = os.path.abspath("non_playoff_team_records.json")
                dst_nf = os.path.join(output_dir, "non_playoff_team_records.json")
                if os.path.exists(src_nf):
                    if os.path.exists(dst_nf):
                        os.remove(dst_nf)
                    shutil.move(src_nf, dst_nf)
            except Exception:
                # Ignore individual JSON move errors but continue
                pass
            print(f"Reports moved to: {output_dir}")
        except Exception as e:
            print(f"Warning: failed to move files to OUTPUT_DIR: {e}")
    else:
        print("Reports generated locally: nfl_team_records.csv, nfl_team_records.html, nfl_all_teams.html")
    
    # Sleep for 8 hours before ending the script, comment this line out if you want to run the script on demand
    if is_docker:
        print("Sleeping for 8 hours...")
        time.sleep(8*60*60)
