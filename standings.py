import argparse
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from flask import Flask, Response, jsonify


STANDINGS_URL = "https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings"
SCHEDULE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"
DISPLAY_COLUMNS = [
    "team",
    "seed",
    "conference",
    "wins",
    "losses",
    "win_pct",
    "sos",
    "quality_score",
    "wins_vs_winning",
    "winning_teams_played",
    "opponents_beaten_vs_winning",
    "playoff_beaten_count",
    "playoff_teams_played",
    "opponents_beaten",
    "playoff_opponents_beaten",
]
LIST_COLUMNS = {
    "opponents_beaten",
    "playoff_opponents_beaten",
    "opponents_beaten_vs_winning",
}

APP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NFL Standings Dashboard</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #0b1220;
      --card: #131c31;
      --muted: #90a4c4;
      --text: #f3f7ff;
      --accent: #4f8cff;
      --accent-2: #75a7ff;
      --border: rgba(255, 255, 255, 0.12);
      --surface: rgba(255, 255, 255, 0.05);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: linear-gradient(180deg, #09111f 0%, #0f1c34 100%);
      color: var(--text);
    }
    .page {
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero, .panel, .stat {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.24);
    }
    .hero {
      padding: 24px;
      margin-bottom: 20px;
    }
    h1, h2, h3, p { margin-top: 0; }
    .hero p, .meta, .empty, .error {
      color: var(--muted);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin: 20px 0;
    }
    .stat {
      padding: 16px;
    }
    .stat-label {
      font-size: 0.85rem;
      color: var(--muted);
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .stat-value {
      font-size: 1.4rem;
      font-weight: 700;
    }
    .panel {
      padding: 20px;
      overflow: hidden;
    }
    .toolbar {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 16px;
    }
    .view-buttons {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    button {
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--surface);
      color: var(--text);
      padding: 10px 14px;
      cursor: pointer;
      transition: 120ms ease-in-out;
    }
    button:hover {
      border-color: var(--accent-2);
      transform: translateY(-1px);
    }
    button.active {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 12px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 1200px;
      background: rgba(4, 10, 18, 0.2);
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #10192d;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }
    th.sort-asc::after { content: " ▲"; }
    th.sort-desc::after { content: " ▼"; }
    tr:hover td {
      background: rgba(255, 255, 255, 0.03);
    }
    .seed-pill {
      display: inline-flex;
      min-width: 32px;
      justify-content: center;
      padding: 3px 8px;
      border-radius: 999px;
      background: rgba(79, 140, 255, 0.16);
      border: 1px solid rgba(79, 140, 255, 0.4);
    }
    .empty, .error {
      padding: 16px 0 4px;
    }
    .error {
      color: #ffb4b4;
    }
    @media (max-width: 720px) {
      .page { padding: 16px; }
      .hero, .panel { padding: 16px; }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>NFL Standings Dashboard</h1>
      <p>The page reads live data from the app database. The server refreshes that database on a schedule and the browser polls for updates automatically.</p>
      <div class="stats" id="stats"></div>
      <p class="meta" id="meta">Loading standings…</p>
    </section>

    <section class="panel">
      <div class="toolbar">
        <div class="view-buttons">
          <button type="button" data-view="playoff" class="active">Current seeded teams</button>
          <button type="button" data-view="non_playoff">Other teams</button>
          <button type="button" data-view="all">All teams</button>
        </div>
      </div>
      <div id="table"></div>
    </section>
  </div>

  <script>
    const POLL_INTERVAL_MS = 60000;
    const VIEW_LABELS = {
      playoff: "Current ESPN-seeded teams",
      non_playoff: "Other teams",
      all: "All teams by quality score"
    };

    let currentView = "playoff";
    let standingsPayload = null;
    let sortState = { column: null, direction: "asc" };

    document.querySelectorAll("[data-view]").forEach((button) => {
      button.addEventListener("click", () => {
        currentView = button.dataset.view;
        document.querySelectorAll("[data-view]").forEach((entry) => entry.classList.remove("active"));
        button.classList.add("active");
        render();
      });
    });

    async function loadStandings() {
      try {
        const response = await fetch("/api/standings", { cache: "no-store" });
        if (!response.ok) {
          throw new Error("Unable to load standings");
        }
        standingsPayload = await response.json();
        render();
      } catch (error) {
        document.getElementById("meta").textContent = error.message;
        document.getElementById("table").innerHTML = `<div class="error">${error.message}</div>`;
      }
    }

    function formatValue(key, value) {
      if (value === null || value === undefined) {
        return "";
      }
      if (Array.isArray(value)) {
        return value.join(", ");
      }
      if (key === "seed" && value !== "") {
        return `<span class="seed-pill">${value}</span>`;
      }
      return String(value);
    }

    function compareValues(left, right) {
      if (typeof left === "number" && typeof right === "number") {
        return left - right;
      }
      return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    }

    function getSortedRows(rows) {
      if (!sortState.column) {
        return rows;
      }
      const column = sortState.column;
      return [...rows].sort((a, b) => {
        const result = compareValues(a[column] ?? "", b[column] ?? "");
        return sortState.direction === "asc" ? result : -result;
      });
    }

    function renderStats() {
      if (!standingsPayload) {
        return;
      }
      const stats = [
        ["Season", standingsPayload.season_year ?? "N/A"],
        ["Teams", standingsPayload.team_count],
        ["Seeded Teams", standingsPayload.playoff.length],
        ["Database Refresh", standingsPayload.last_refreshed_at ? new Date(standingsPayload.last_refreshed_at).toLocaleString() : "Not loaded yet"]
      ];
      document.getElementById("stats").innerHTML = stats.map(([label, value]) => `
        <div class="stat">
          <div class="stat-label">${label}</div>
          <div class="stat-value">${value}</div>
        </div>
      `).join("");
      document.getElementById("meta").textContent = standingsPayload.last_error
        ? `Latest refresh failed. Showing last good data. ${standingsPayload.last_error}`
        : `Browser polling every ${POLL_INTERVAL_MS / 1000}s. Updated from the latest successful database refresh.`;
    }

    function renderTable() {
      const container = document.getElementById("table");
      if (!standingsPayload) {
        container.innerHTML = '<div class="empty">No standings are available yet.</div>';
        return;
      }

      const rows = getSortedRows(standingsPayload[currentView] || []);
      if (!rows.length) {
        container.innerHTML = '<div class="empty">The database has not been populated yet.</div>';
        return;
      }

      const columns = Object.keys(rows[0]);
      const headers = columns.map((column) => {
        const sortClass = sortState.column === column ? `sort-${sortState.direction}` : "";
        return `<th class="${sortClass}" data-column="${column}">${column}</th>`;
      }).join("");

      const body = rows.map((row) => `
        <tr>${columns.map((column) => `<td>${formatValue(column, row[column])}</td>`).join("")}</tr>
      `).join("");

      container.innerHTML = `
        <h2>${VIEW_LABELS[currentView]}</h2>
        <div class="table-wrap">
          <table>
            <thead><tr>${headers}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;

      container.querySelectorAll("th[data-column]").forEach((header) => {
        header.addEventListener("click", () => {
          const nextColumn = header.dataset.column;
          if (sortState.column === nextColumn) {
            sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
          } else {
            sortState.column = nextColumn;
            sortState.direction = "asc";
          }
          renderTable();
        });
      });
    }

    function render() {
      renderStats();
      renderTable();
    }

    loadStandings();
    setInterval(loadStandings, POLL_INTERVAL_MS);
  </script>
</body>
</html>
"""

_scheduler_lock = threading.Lock()
_scheduler_started = False


def _fetch_json(url: str) -> dict:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def _stat(entry: dict, name: str):
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            return stat.get("value")
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", ".")).resolve()


def get_database_path() -> Path:
    configured_path = os.environ.get("DATABASE_PATH")
    if configured_path:
        return Path(configured_path).resolve()
    return get_data_dir() / "standings.db"


def get_export_dir() -> Path:
    configured_dir = os.environ.get("OUTPUT_DIR")
    if configured_dir:
        return Path(configured_dir).resolve()
    return get_data_dir() / "exports"


def get_refresh_interval_seconds() -> int:
    value = os.environ.get("REFRESH_INTERVAL_SECONDS", "3600")
    return max(int(value), 60)


@contextmanager
def db_connection():
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_records (
                team_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                win_pct REAL NOT NULL,
                point_diff REAL NOT NULL,
                div_wins INTEGER NOT NULL,
                div_losses INTEGER NOT NULL,
                points_for INTEGER NOT NULL,
                points_against INTEGER NOT NULL,
                espn_playoff_seed INTEGER,
                conf_record TEXT,
                conference TEXT NOT NULL,
                sos REAL NOT NULL,
                opponents_beaten_json TEXT NOT NULL,
                playoff_opponents_beaten_json TEXT NOT NULL,
                playoff_beaten_count TEXT NOT NULL,
                playoff_teams_played TEXT NOT NULL,
                in_playoffs INTEGER NOT NULL,
                seed INTEGER,
                wins_vs_winning TEXT NOT NULL,
                opponents_beaten_vs_winning_json TEXT NOT NULL,
                winning_teams_played TEXT NOT NULL,
                quality_score REAL NOT NULL,
                last_refreshed_at TEXT NOT NULL,
                season_year INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                refreshed_at TEXT NOT NULL,
                season_year INTEGER,
                team_count INTEGER,
                status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
                error_message TEXT
            )
            """
        )


def get_season_year() -> int | None:
    try:
        data = _fetch_json(STANDINGS_URL)
        season = data.get("season") or {}
        year = season.get("year")
        if year is not None:
            return int(year)
        year = data.get("seasonYear")
        return int(year) if year is not None else None
    except Exception:
        return None


def get_standings() -> list[dict]:
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

            conf_record = None
            for stat in entry.get("stats", []):
                if stat.get("name") == "vs. Conf.":
                    conf_record = stat.get("value")
                    break

            teams.append(
                {
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
                }
            )
    return teams


def get_team_results(team_id: str, season_year: int | None = None):
    base = SCHEDULE_URL.format(team_id=team_id)
    url = f"{base}?season={season_year}&seasontype=2" if season_year else f"{base}?seasontype=2"
    try:
        data = _fetch_json(url)
    except requests.HTTPError:
        return [], {}, []

    opponents_beaten = []
    h2h_records = {}
    all_opponents = []

    for event in data.get("events", []):
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        me = next((competitor for competitor in competitors if competitor.get("id") == str(team_id)), None)
        opponent = next((competitor for competitor in competitors if competitor.get("id") != str(team_id)), None)
        if not me or not opponent:
            continue

        opponent_name = opponent.get("displayName") or opponent.get("team", {}).get("displayName")
        all_opponents.append(opponent_name)

        if me.get("winner"):
            opponents_beaten.append(opponent_name)

        if opponent_name not in h2h_records:
            h2h_records[opponent_name] = {"wins": 0, "losses": 0}
        if me.get("winner"):
            h2h_records[opponent_name]["wins"] += 1
        else:
            h2h_records[opponent_name]["losses"] += 1

    return opponents_beaten, h2h_records, all_opponents


def build_dataset() -> tuple[pd.DataFrame, int | None]:
    standings = get_standings()
    all_schedules = {}
    season_year = get_season_year()

    for team in standings:
        all_schedules[team["id"]] = get_team_results(team["id"], season_year)

    win_pct_map = {team["team"]: team["win_pct"] for team in standings}
    playoff_teams = {
        team["team"]: team["espn_playoff_seed"]
        for team in standings
        if team["espn_playoff_seed"] is not None and team["espn_playoff_seed"] <= 7
    }

    dataset = []
    for team in standings:
        beaten, _, all_opponents = all_schedules[team["id"]]

        sos = sum(win_pct_map.get(opponent, 0) for opponent in all_opponents) / len(all_opponents) if all_opponents else 0.0
        team["sos"] = round(sos, 3)

        beaten_counts = {}
        for opponent in beaten:
            beaten_counts[opponent] = beaten_counts.get(opponent, 0) + 1
        team["opponents_beaten"] = [
            f"{opponent} (x{count})" if count > 1 else opponent for opponent, count in beaten_counts.items()
        ]

        playoff_beaten = [opponent for opponent in beaten if opponent in playoff_teams]
        playoff_beaten_counts = {}
        for opponent in playoff_beaten:
            playoff_beaten_counts[opponent] = playoff_beaten_counts.get(opponent, 0) + 1
        team["playoff_opponents_beaten"] = [
            f"{opponent} (x{count})" if count > 1 else opponent
            for opponent, count in playoff_beaten_counts.items()
        ]

        unique_playoff_beaten = len(set(playoff_beaten))
        total_playoff_beaten = len(playoff_beaten)
        duplicate_playoff_wins = total_playoff_beaten - unique_playoff_beaten
        team["playoff_beaten_count"] = (
            f"{unique_playoff_beaten} ({duplicate_playoff_wins})" if duplicate_playoff_wins > 0 else str(unique_playoff_beaten)
        )

        playoff_played = set()
        playoff_games_count = 0
        for opponent in beaten:
            if opponent in playoff_teams:
                playoff_played.add(opponent)
                playoff_games_count += 1
        for other_team in standings:
            if other_team["team"] not in playoff_teams:
                continue
            other_beaten, _, _ = all_schedules[other_team["id"]]
            if team["team"] in other_beaten:
                playoff_played.add(other_team["team"])
                playoff_games_count += 1

        unique_playoff_teams = len(playoff_played)
        duplicate_playoff_games = playoff_games_count - unique_playoff_teams
        team["playoff_teams_played"] = (
            f"{unique_playoff_teams} ({duplicate_playoff_games})"
            if duplicate_playoff_games > 0
            else str(unique_playoff_teams)
        )
        team["in_playoffs"] = team["team"] in playoff_teams
        team["seed"] = team["espn_playoff_seed"]

        total_wins_vs_winning = sum(1 for opponent in beaten if win_pct_map.get(opponent, 0) > 0.5)
        beaten_winning = [opponent for opponent in beaten_counts if win_pct_map.get(opponent, 0) > 0.5]
        team["opponents_beaten_vs_winning"] = [
            f"{opponent} (x{beaten_counts[opponent]})" if beaten_counts[opponent] > 1 else opponent
            for opponent in beaten_winning
        ]

        unique_wins_vs_winning = len(beaten_winning)
        duplicate_wins_vs_winning = total_wins_vs_winning - unique_wins_vs_winning
        team["wins_vs_winning"] = (
            f"{unique_wins_vs_winning} ({duplicate_wins_vs_winning})"
            if duplicate_wins_vs_winning > 0
            else str(unique_wins_vs_winning)
        )

        winning_played = set()
        winning_games_count = 0
        for opponent in beaten:
            if win_pct_map.get(opponent, 0) > 0.5:
                winning_played.add(opponent)
                winning_games_count += 1
        for other_team in standings:
            if other_team.get("win_pct", 0) <= 0.5:
                continue
            other_beaten, _, _ = all_schedules[other_team["id"]]
            if team["team"] in other_beaten:
                winning_played.add(other_team["team"])
                winning_games_count += 1

        unique_winning_teams = len(winning_played)
        duplicate_winning_games = winning_games_count - unique_winning_teams
        team["winning_teams_played"] = (
            f"{unique_winning_teams} ({duplicate_winning_games})"
            if duplicate_winning_games > 0
            else str(unique_winning_teams)
        )

        quality_score = (team["win_pct"] * 40) + (team["sos"] * 20) + (total_wins_vs_winning * 2.5) + (total_playoff_beaten * 4)
        team["quality_score"] = round(quality_score, 2)
        dataset.append(team)

    return pd.DataFrame(dataset), season_year


def validate_dataset(frame: pd.DataFrame) -> None:
    conditions = [
        isinstance(frame, pd.DataFrame),
        not frame.empty,
        len(frame.index) == 32,
        "team" in frame.columns and not frame["team"].isnull().any(),
        "win_pct" in frame.columns and not frame["win_pct"].isnull().any(),
    ]
    if not all(conditions):
        raise ValueError("Dataset validation failed; refusing to overwrite database with incomplete data.")


def dataframe_to_records(frame: pd.DataFrame) -> list[dict]:
    normalized = frame.where(pd.notnull(frame), None)
    return normalized.to_dict(orient="records")


def write_exports(frame: pd.DataFrame) -> None:
    export_dir = get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    frame.to_csv(export_dir / "nfl_team_records.csv", index=False)

    records = dataframe_to_records(frame)
    playoff_records = [record for record in records if record["in_playoffs"]]
    non_playoff_records = [record for record in records if not record["in_playoffs"]]

    with open(export_dir / "nfl_team_records.json", "w", encoding="utf-8") as output_file:
        json.dump(records, output_file, ensure_ascii=False, indent=2)
    with open(export_dir / "playoff_team_records.json", "w", encoding="utf-8") as output_file:
        json.dump(playoff_records, output_file, ensure_ascii=False, indent=2)
    with open(export_dir / "non_playoff_team_records.json", "w", encoding="utf-8") as output_file:
        json.dump(non_playoff_records, output_file, ensure_ascii=False, indent=2)


def record_refresh_failure(refreshed_at: str, error_message: str) -> None:
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO refresh_runs (refreshed_at, season_year, team_count, status, error_message)
            VALUES (?, NULL, NULL, 'failed', ?)
            """,
            (refreshed_at, error_message),
        )


def save_dataset(frame: pd.DataFrame, season_year: int | None, refreshed_at: str) -> None:
    records = dataframe_to_records(frame)
    with db_connection() as connection:
        connection.execute("DELETE FROM team_records")
        for record in records:
            connection.execute(
                """
                INSERT INTO team_records (
                    team_id, team, wins, losses, win_pct, point_diff, div_wins, div_losses,
                    points_for, points_against, espn_playoff_seed, conf_record, conference, sos,
                    opponents_beaten_json, playoff_opponents_beaten_json, playoff_beaten_count,
                    playoff_teams_played, in_playoffs, seed, wins_vs_winning,
                    opponents_beaten_vs_winning_json, winning_teams_played, quality_score,
                    last_refreshed_at, season_year
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["team"],
                    record["wins"],
                    record["losses"],
                    record["win_pct"],
                    record["point_diff"],
                    record["div_wins"],
                    record["div_losses"],
                    record["points_for"],
                    record["points_against"],
                    record["espn_playoff_seed"],
                    record["conf_record"],
                    record["conference"],
                    record["sos"],
                    json.dumps(record["opponents_beaten"] or []),
                    json.dumps(record["playoff_opponents_beaten"] or []),
                    record["playoff_beaten_count"],
                    record["playoff_teams_played"],
                    int(bool(record["in_playoffs"])),
                    record["seed"],
                    record["wins_vs_winning"],
                    json.dumps(record["opponents_beaten_vs_winning"] or []),
                    record["winning_teams_played"],
                    record["quality_score"],
                    refreshed_at,
                    season_year,
                ),
            )
        connection.execute(
            """
            INSERT INTO refresh_runs (refreshed_at, season_year, team_count, status, error_message)
            VALUES (?, ?, ?, 'success', NULL)
            """,
            (refreshed_at, season_year, len(records)),
        )


def refresh_database() -> bool:
    refreshed_at = utc_now_iso()
    try:
        frame, season_year = build_dataset()
        validate_dataset(frame)
        save_dataset(frame, season_year, refreshed_at)
        write_exports(frame)
        print(f"[{refreshed_at}] Refreshed {len(frame.index)} teams into {get_database_path()}")
        return True
    except Exception as error:
        error_message = str(error)
        record_refresh_failure(refreshed_at, error_message)
        print(f"[{refreshed_at}] Refresh failed: {error_message}")
        return False


def decode_row(row: sqlite3.Row) -> dict:
    values = dict(row)
    values["in_playoffs"] = bool(values["in_playoffs"])
    values["opponents_beaten"] = json.loads(values.pop("opponents_beaten_json"))
    values["playoff_opponents_beaten"] = json.loads(values.pop("playoff_opponents_beaten_json"))
    values["opponents_beaten_vs_winning"] = json.loads(values.pop("opponents_beaten_vs_winning_json"))
    return values


def display_record(record: dict) -> dict:
    ordered = {}
    for column in DISPLAY_COLUMNS:
        ordered[column] = record.get(column)
    return ordered


def standings_sort_key(record: dict) -> tuple:
    conference = record.get("conference") or ""
    seed = record.get("seed")
    return conference, seed if seed is not None else 99, -record.get("quality_score", 0)


def fetch_standings_payload() -> dict:
    with db_connection() as connection:
        team_rows = connection.execute("SELECT * FROM team_records").fetchall()
        latest_success = connection.execute(
            """
            SELECT refreshed_at, season_year, team_count
            FROM refresh_runs
            WHERE status = 'success'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        latest_run = connection.execute(
            """
            SELECT status, error_message
            FROM refresh_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    records = [decode_row(row) for row in team_rows]
    playoff = sorted((record for record in records if record["in_playoffs"]), key=standings_sort_key)
    non_playoff = sorted((record for record in records if not record["in_playoffs"]), key=standings_sort_key)
    all_teams = sorted(records, key=lambda record: (-record["quality_score"], record["team"]))

    return {
        "season_year": latest_success["season_year"] if latest_success else None,
        "team_count": latest_success["team_count"] if latest_success else len(records),
        "last_refreshed_at": latest_success["refreshed_at"] if latest_success else None,
        "last_error": latest_run["error_message"] if latest_run and latest_run["status"] == "failed" else None,
        "playoff": [display_record(record) for record in playoff],
        "non_playoff": [display_record(record) for record in non_playoff],
        "all": [display_record(record) for record in all_teams],
    }


def refresh_loop() -> None:
    refresh_database()
    interval = get_refresh_interval_seconds()
    while True:
        time.sleep(interval)
        refresh_database()


def start_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        thread = threading.Thread(target=refresh_loop, name="standings-refresh", daemon=True)
        thread.start()
        _scheduler_started = True


def create_app(start_background_refresh: bool = True) -> Flask:
    init_db()
    if start_background_refresh:
        start_scheduler()

    app = Flask(__name__)

    @app.get("/")
    def index():
        return Response(APP_HTML, mimetype="text/html")

    @app.get("/api/standings")
    def api_standings():
        return jsonify(fetch_standings_payload())

    @app.get("/health")
    def health():
        payload = fetch_standings_payload()
        return jsonify(
            {
                "ok": payload["team_count"] > 0,
                "team_count": payload["team_count"],
                "last_refreshed_at": payload["last_refreshed_at"],
                "database_path": str(get_database_path()),
            }
        )

    return app


app = create_app(start_background_refresh=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve and refresh the NFL standings dashboard.")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "refresh-once"],
        help="serve the web app or refresh the database once",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    if args.command == "refresh-once":
        return 0 if refresh_database() else 1

    runtime_app = create_app(start_background_refresh=True)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    runtime_app.run(host=host, port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
