# GitHub Actions Setup

This repository uses GitHub Actions to automatically update NFL standings data.

## Workflow: Update NFL Standings

**File:** `.github/workflows/update-standings.yml`

### Schedule
- Runs every **Tuesday at 8:00 AM UTC**
- Can be manually triggered via GitHub UI (Actions tab → Update NFL Standings → Run workflow)

### What it does
1. Checks out the repository
2. Sets up Python 3.12
3. Installs dependencies from `requirements.txt`
4. Runs `standings.py` to fetch latest data
5. Commits and pushes updated CSV/HTML files back to the repo

### Manual Trigger
1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select **Update NFL Standings** workflow
4. Click **Run workflow** → **Run workflow**

### Outputs
- `nfl_team_records.csv` - Updated standings data
- `nfl_team_records.html` - Visual report with timestamp

### Setup Requirements
- Repository must allow GitHub Actions (enabled by default)
- No secrets needed - uses public ESPN API
- Commits are made by `github-actions[bot]`

### Customization
To change the schedule, edit the cron expression in the workflow file:
```yaml
schedule:
  - cron: '0 8 * * 2'  # Min Hour Day Month DayOfWeek
```

Examples:
- Daily at 8 AM: `'0 8 * * *'`
- Every 6 hours: `'0 */6 * * *'`
- Mondays and Thursdays at 9 AM: `'0 9 * * 1,4'`
