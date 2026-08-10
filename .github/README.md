# GitHub Actions Setup

This repository uses GitHub Actions to deploy the NFL standings app.

## Workflow: Update NFL Standings

**File:** `.github/workflows/update-standings.yml`

### Triggers
- Pushes to `main`
- Manual runs from the Actions tab

### What it does
1. Checks out the repository
2. Deploys the latest code to the VPS over SSH
3. Rebuilds the Docker image
4. Restarts the long-running web container
5. Leaves periodic database refreshes to the app itself

### Manual Trigger
1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select **Update NFL Standings** workflow
4. Click **Run workflow** → **Run workflow**

### Runtime Outputs
- Web UI on port `8000`
- SQLite database at `data/standings.db`
- Snapshot exports under `data/exports/`

### Setup Requirements
- GitHub Actions secrets for VPS access
- A host with Docker installed
- Port `8000` reachable if you want the UI public
