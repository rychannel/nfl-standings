# NFL Standings Docker Setup

## Build and Run

### Using Docker directly:
```bash
docker build -t nfl-standings .
docker run --rm -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e DATA_DIR=/app/data \
  -e DATABASE_PATH=/app/data/standings.db \
  -e OUTPUT_DIR=/app/data/exports \
  -e REFRESH_INTERVAL_SECONDS=3600 \
  nfl-standings
```

### Using Docker Compose:
```bash
docker-compose up --build
```

Open `http://localhost:8000` after the container starts.

## Runtime Behavior

- The container runs a web server on port `8000`
- A background refresh task loads fresh standings into SQLite every `REFRESH_INTERVAL_SECONDS`
- The browser pulls current standings from `/api/standings`
- JSON and CSV snapshot exports are written under `data/exports/`

## Stored Files

- `data/standings.db` - SQLite database used by the app
- `data/exports/nfl_team_records.csv` - Latest CSV snapshot
- `data/exports/nfl_team_records.json` - Latest JSON snapshot

## Environment

- `PORT` - web server port, default `8000`
- `DATA_DIR` - base directory for database and exports
- `DATABASE_PATH` - explicit SQLite file path
- `OUTPUT_DIR` - optional export directory for JSON/CSV snapshots
- `REFRESH_INTERVAL_SECONDS` - refresh cadence, default `3600`
