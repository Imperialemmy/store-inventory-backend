# Backend deployment

The backend auto-deploys to the production VPS via GitHub Actions
(`.github/workflows/deploy.yml`) on every push to `main` (i.e. every merged
PR). You can also trigger it manually from the repo's **Actions** tab
("Deploy backend to VPS" → "Run workflow").

## What the deploy does (on the VPS)

1. `git reset --hard origin/main` — mirror the latest `main`
   (gitignored files like `.env`, the database and `media/` are untouched)
2. Activate the virtualenv (`.venv` or `venv`)
3. `pip install -r requirements.txt`
4. `python manage.py migrate --noinput`
5. `python manage.py collectstatic --noinput`
6. `sudo systemctl restart <service>`

## Required GitHub repository secrets

Add these under **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value | Example |
| --- | --- | --- |
| `VPS_HOST` | Server IP or hostname | `157.230.229.31` |
| `VPS_USER` | SSH user | `root` |
| `VPS_SSH_KEY` | **Private** key whose public key is in the server's `~/.ssh/authorized_keys` | (full PEM contents) |
| `VPS_PROJECT_DIR` | Absolute path to the backend project on the server | `/root/store-inventory-backend` |
| `VPS_SERVICE` | systemd unit name that runs the app | `akinfolu` / `gunicorn` / `daphne` |
| `VPS_PORT` | (optional) SSH port, defaults to `22` | `22` |

## One-time key setup

On a machine you trust (or the server), create a dedicated deploy key:

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f deploy_key -N ""
# add the PUBLIC key to the server:
ssh-copy-id -i deploy_key.pub root@157.230.229.31
# then paste the PRIVATE key (deploy_key) into the VPS_SSH_KEY secret
```

If `VPS_USER` is not root, ensure it can run `sudo systemctl restart <service>`
without a password prompt (via a sudoers NOPASSWD rule).
