# GitHub Secrets Setup for Auto-Deployment

To enable automatic deployment to your VPS, add these secrets to your GitHub repository:

## Required Secrets

Go to: **Repository Settings → Secrets and variables → Actions → New repository secret**

### 1. VPS_HOST
- **Value:** Your VPS IP address or hostname
- **Example:** `192.168.1.100` or `myserver.example.com`

### 2. VPS_USER
- **Value:** SSH username for your VPS
- **Example:** `root` or your username

### 3. VPS_SSH_KEY
- **Value:** Your private SSH key (the entire key including `-----BEGIN` and `-----END` lines)
- **How to get it:**
  ```bash
  # On your local machine
  cat ~/.ssh/id_rsa
  # Copy the entire output
  ```
- **Note:** If you don't have an SSH key, generate one:
  ```bash
  ssh-keygen -t rsa -b 4096 -C "github-actions"
  # Then copy the public key to your VPS:
  ssh-copy-id your-user@your-vps-ip
  ```

### 4. VPS_PROJECT_PATH (Optional)
- **Value:** Full path to your project on the VPS
- **Default:** `/home/$USER/nfl-standings`
- **Example:** `/home/myuser/projects/nfl-standings`

### 5. VPS_PORT (Optional)
- **Value:** SSH port if not using default 22
- **Default:** `22`
- **Example:** `2222`

## Setup Steps

1. **Add secrets to GitHub:**
   - Go to your repo → Settings → Secrets and variables → Actions
   - Click "New repository secret" for each one

2. **Ensure your VPS is set up:**
   ```bash
   # SSH into your VPS
   ssh your-user@your-vps-ip
   
   # Navigate to project directory
   cd /home/your-user/nfl-standings
   
   # Make sure git is configured
   git config --global user.email "you@example.com"
   git config --global user.name "Your Name"
   
   # Ensure Docker and Docker Compose are installed
   docker --version
   docker-compose --version
   ```

3. **Test deployment:**
   - Make a small change to README.md
   - Commit and push to main branch
   - Check Actions tab to see deployment progress

## Workflow Behavior

- **Push to main:** Triggers automatic deployment to VPS
- **Schedule (Tuesday 8 AM):** Updates standings and commits to repo
- **Manual trigger:** Updates standings without deployment

## Troubleshooting

- **Permission denied:** Check that your SSH key is correct and added to VPS `~/.ssh/authorized_keys`
- **Git pull fails:** Ensure your VPS has access to the repo (use HTTPS or add deploy key)
- **Docker fails:** Check Docker service is running: `sudo systemctl status docker`
