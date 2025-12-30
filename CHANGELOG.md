# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-12-29

### Added
- **Core Functionality**
  - NFL standings data fetching from ESPN API
  - Team schedule and opponent tracking from ESPN API
  - Playoff picture calculation (14 teams - 7 per conference)
  - Division structure support (AFC/NFC with 4 divisions each)
  - Proper playoff structure: 4 division winners (seeds 1-4) + 3 wildcards (seeds 5-7) per conference

- **NFL Tiebreaker System**
  - Official NFL tiebreaker rules implementation for playoff seeding
  - Head-to-head record comparison
  - Division record comparison
  - Point differential tiebreaker
  - Recursive tiebreaker application for 3+ team ties
  - ESPN playoff seed integration for official seeding

- **Statistics & Analysis**
  - Opponents beaten tracking for each team
  - Playoff opponents beaten tracking
  - Playoff teams played count with duplicate game tracking
  - Win-loss record tracking
  - Conference affiliation
  - Division win-loss records
  - Point differential (points for/against)

- **Duplicate Game Tracking**
  - Duplicate wins indicator (e.g., "3 (1)" = 3 unique teams, 1 duplicate win)
  - Duplicate games played indicator
  - Team-by-team duplicate notation (e.g., "Carolina Panthers (x2)")
  - Applied to both all opponents and playoff opponents columns

- **Output Formats**
  - Console output with formatted tables
  - CSV export (`nfl_team_records.csv`) with all data columns
  - HTML report (`nfl_team_records.html`) with:
    - Sortable columns (click headers to sort)
    - UTC timestamp
    - Separate playoff and non-playoff team sections
    - Clean, readable styling

- **Column Headers**
  - team: Team name
  - seed: ESPN official playoff seed (1-16)
  - conference: AFC or NFC
  - wins: Season wins
  - losses: Season losses
  - win_pct: Win percentage
  - playoff_beaten (dups): Unique playoff teams beaten (duplicates in parentheses)
  - playoff_teams_played (dups): Unique playoff teams played (duplicates in parentheses)
  - opponents_beaten: All opponents beaten with duplicate notation
  - playoff_opponents_beaten: Playoff opponents beaten with duplicate notation

- **Docker Support**
  - Dockerfile for containerized deployment
  - docker-compose.yml configuration
  - Environment variable support (DOCKER, OUTPUT_DIR)
  - Automatic file movement to output directory when running in Docker
  - 8-hour sleep cycle for periodic updates

- **CI/CD**
  - GitHub Actions workflow for automated deployment
  - Deploy on push to main branch
  - SSH deployment to Debian VPS
  - Docker Compose orchestration

- **Documentation**
  - Deployment instructions
  - Environment configuration guide
  - Docker setup documentation

- **Licensing**
  - Non-Commercial License with attribution requirement
  - Commercial use requires separate licensing agreement
  - Copyright 2025 Ryan Murphy

### Technical Details
- Python 3.12+ compatibility
- Dependencies: requests, pandas, beautifulsoup4, lxml
- ESPN JSON API endpoints for real-time data
- Hardcoded NFL division structure (8 divisions, 32 teams)
- Proper handling of division-to-conference mapping

### Data Sources
- Standings: `https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings`
- Schedules: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule`

### Known Limitations
- Tiebreaker implementation uses available ESPN stats (head-to-head, division record, point differential)
- Some advanced NFL tiebreakers (common games, strength of schedule, strength of victory) not fully implemented
- Relies on ESPN playoff seed for final seeding authority

### Future Considerations
- Additional tiebreaker criteria implementation
- Conference record tracking and display
- Common games analysis
- Strength of schedule/victory calculations
- Historical data tracking
- Playoff scenario predictions
