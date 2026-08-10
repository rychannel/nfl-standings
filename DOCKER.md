# NFL Standings Docker Setup

## Build and Run

### Using Docker directly:
```bash
docker build -t nfl-standings .
docker run --rm -v $(pwd)/output:/app/output nfl-standings
```

### Using Docker Compose:
```bash
docker-compose up --build
```

## Output Files

The script generates:
- `nfl_team_records.csv` - CSV with all team data and playoff information
- `nfl_team_records.html` - Formatted HTML report with playoff and non-playoff tables

Output files are saved to the `output/` directory when using volumes.

## Environment

- Python 3.12 (slim image)
- Dependencies: pandas, requests
- Container name: `nfl-standings`
