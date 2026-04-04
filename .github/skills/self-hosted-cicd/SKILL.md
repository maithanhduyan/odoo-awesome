---
name: self-hosted-cicd
description: "Self-hosted CI/CD for Docker services on VPS. Use for: creating deploy scripts with canary health-check and auto-rollback; setting up git bare repos with post-receive hooks for push-to-deploy; configuring env-driven Docker builds (envsubst templates); troubleshooting failed deploys or rollbacks; adding new services to the git-push deploy pipeline; modifying branch→deploy mappings."
argument-hint: "Describe what you want to deploy, which service, or what deploy problem to solve"
---

# Self-Hosted CI/CD — Git Push → Canary → Deploy

Zero-downtime deployment pipeline for Docker services on a single VPS, using git hooks + canary health checks + auto-rollback. No external CI service required.

## When to Use

- Setting up push-to-deploy for a new Docker service
- Creating or modifying deploy scripts with health-check gates
- Troubleshooting failed deployments or rollbacks
- Adding branch→deploy mappings to post-receive hooks
- Converting hardcoded configs to env-driven templates (envsubst)
- Adapting a service for both VPS (docker-compose) and PaaS (Railway)

## Architecture

```
Developer Machine                        VPS (/home/)
┌──────────────┐    git push ssh    ┌──────────────────────────────┐
│  Working Copy │ ─────────────────→│  /home/<service>.git  (bare) │
│  (local)      │                   │       │ post-receive hook     │
└──────────────┘                    │       ▼                      │
                                    │  checkout → /home/<service>/ │
                                    │       │                      │
                                    │       ▼                      │
                                    │  deploy.sh                   │
                                    │   1. Build new image         │
                                    │   2. Tag old → :rollback     │
                                    │   3. Canary (health check)   │
                                    │   4. Swap production         │
                                    │   5. Verify or auto-rollback │
                                    └──────────────────────────────┘
```

### Key Principle: Production Never Stops Unless Replacement is Verified

The running container is **never** stopped until a canary container proves the new image is healthy. If anything fails, the old container keeps running.

## Components

### 1. Env-Driven Config (envsubst)

Instead of hardcoded config files, use templates with `${VAR}` placeholders rendered at container startup.

**Files:**
- `conf/<service>.conf.template` — config with `${VAR}` placeholders
- `.env` — variable values for docker-compose (VPS)
- `.env.example` — documented template for new deployments
- `entrypoint.sh` — sets defaults + runs `envsubst`
- `Dockerfile` — must install `gettext-base` (provides `envsubst`) and `gosu`

**Pattern:**
```dockerfile
# Dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gettext-base gosu
COPY conf/odoo.conf.template /etc/odoo/odoo.conf.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

```bash
# entrypoint.sh — key section
export DB_HOST="${DB_HOST:-postgres}"
export DB_PORT="${DB_PORT:-5432}"
# ... all vars with sensible defaults ...

envsubst < /etc/odoo/odoo.conf.template > /etc/odoo/odoo.conf
exec gosu odoo "$@"
```

```ini
# conf/odoo.conf.template
[options]
db_host = ${DB_HOST}
db_port = ${DB_PORT}
```

**docker-compose.yaml** passes env vars (from `.env`) into the container:
```yaml
environment:
  - DB_HOST=${POSTGRES_HOST:-postgres}
  # ... all vars ...
```

**Critical:** Remove hardcoded config volume mounts (`./conf/odoo.conf:/etc/odoo/odoo.conf:ro`). The entrypoint generates the config from template.

**PaaS compatibility:** On Railway/Render, set env vars in the dashboard — same entrypoint, same template, no `.env` file needed.

### 2. Deploy Script (deploy.sh)

The deploy script implements a canary pattern:

```
Build image → Save rollback tag → Start canary → Health check
                                                     │
                              ┌────────── FAIL ──────┘──── OK ──────┐
                              ▼                                     ▼
                    ABORT (prod untouched)                  Swap production
                                                                │
                                                   ┌─── FAIL ──┘── OK ─┐
                                                   ▼                    ▼
                                             Auto-rollback          Done ✓
```

**Key implementation details:**

- **Canary runs on alternate port** (e.g., 18069) with `WORKERS=0` (single-process, fast startup)
- **Health check uses `docker exec`** (not port mapping) to avoid conflicts:
  ```bash
  docker exec "$CANARY_NAME" curl -sf "http://localhost:${port}/web/health"
  ```
- **Canary has `traefik.enable=false`** label so it doesn't receive real traffic
- **Rollback image** is tagged before swap: `docker tag <old-sha> <image>:rollback`
- **Env extraction** for canary uses `docker compose config --format json` → python → env file

**Three modes:**
```bash
./deploy.sh              # Full: build + canary + swap
./deploy.sh --no-build   # Config-only: canary + swap (no rebuild)
./deploy.sh --rollback   # Force rollback to :rollback tag
```

### 3. Git Bare Repo + Post-Receive Hook

**Setup:**
```bash
# Create bare repo (push target)
git init --bare /home/<service>.git

# Init working repo
cd /home/<service>
git init && git add -A && git commit -m "init"
git remote add deploy /home/<service>.git
git push deploy main
```

**Branch → deploy mapping** in `post-receive`:

| Branch Pattern | Deploy Mode | When to Use |
|----------------|-------------|-------------|
| `main` | Full (build + canary + swap) | Code/Dockerfile changes |
| `hotfix/*` | Full (build + canary + swap) | Urgent production fixes |
| `config/*` | Config-only (`--no-build`) | `.env` or config template changes |
| Any other | Skip (no deploy) | Feature development, safe to push |

**Hook pattern:**
```bash
#!/bin/bash
set -uo pipefail
WORK_TREE="/home/<service>"
DEPLOY_SCRIPT="${WORK_TREE}/deploy.sh"

while read -r OLD_REV NEW_REV REF_NAME; do
    BRANCH="${REF_NAME#refs/heads/}"
    case "$BRANCH" in
        main|hotfix/*) MODE="full" ;;
        config/*)      MODE="config-only" ;;
        *)             continue ;;  # skip
    esac
    GIT_WORK_TREE="$WORK_TREE" git checkout -f "$BRANCH"
    if [[ "$MODE" == "config-only" ]]; then
        bash "$DEPLOY_SCRIPT" --no-build
    else
        bash "$DEPLOY_SCRIPT"
    fi
done
```

## Applying to a New Service

To add CI/CD to any Docker service:

1. **Create env template:**
   - `conf/<name>.conf.template` with `${VAR}` placeholders
   - `entrypoint.sh` with defaults + `envsubst`
   - Update `Dockerfile` to install `gettext-base`, copy template, set entrypoint

2. **Create deploy.sh** — copy from `odoo-19/deploy.sh`, update:
   - `IMAGE_NAME` — matches `docker compose build` output
   - `PROD_CONTAINER` — your container name
   - `CANARY_PORT` — unused port
   - Health check URL path (e.g., `/web/health`, `/healthz`, `/api/health`)

3. **Create bare repo + hook:**
   ```bash
   git init --bare /home/<service>.git
   cp /home/odoo-19.git/hooks/post-receive /home/<service>.git/hooks/post-receive
   # Edit: WORK_TREE, DEPLOY_SCRIPT paths
   chmod +x /home/<service>.git/hooks/post-receive
   ```

4. **Init + push:**
   ```bash
   cd /home/<service>
   git init && git add -A && git commit -m "init"
   git remote add deploy /home/<service>.git
   git push deploy main
   ```

## Troubleshooting

### Canary fails health check

```bash
# Check canary logs
docker logs odoo-19-canary 2>&1 | tail -30

# Common causes:
# - DBFILTER empty → hits wrong database → KeyError: 'ir.http'
# - Missing Python packages in image
# - Redis/DB not reachable from canary (network issue)
```

### envsubst not found

Install `gettext-base` in Dockerfile:
```dockerfile
RUN apt-get install -y --no-install-recommends gettext-base
```

### gosu not found

Install in Dockerfile:
```dockerfile
RUN apt-get install -y --no-install-recommends gosu
```

### Canary env file empty

The `docker compose config --format json` output must be written to a temp file first, then parsed by python (heredoc consumes stdin, so pipe+heredoc doesn't work):
```bash
# WRONG: pipe + heredoc — stdin conflict
docker compose config --format json | python3 <<'EOF'
...
EOF

# CORRECT: temp file
docker compose config --format json > /tmp/config.json
python3 <<'PYEOF'
import json
with open('/tmp/config.json') as f:
    cfg = json.load(f)
...
PYEOF
```

### Rollback image not found

Rollback image is only created during deploy. If you've never deployed, there's no `:rollback` tag:
```bash
docker image inspect odoo-19-odoo:rollback  # check if exists
```

### Deploy log location

All hook + deploy output goes to `/var/log/odoo-19-deploy.log`.

## Reference: Odoo 19 File Map

```
/home/odoo-19/                    # Working tree (production)
├── .env                          # Secrets + env vars (gitignored)
├── .env.example                  # Template for new deployments
├── .gitignore
├── Dockerfile                    # Installs gettext-base, gosu, copies template
├── deploy.sh                     # Canary deploy script
├── docker-compose.yaml           # All env vars passed to container
├── entrypoint.sh                 # Defaults + envsubst + gosu
├── conf/
│   ├── odoo.conf                 # Generated at runtime (gitignored in container)
│   └── odoo.conf.template        # Source of truth with ${VAR} placeholders
├── addons/                       # Custom Odoo modules (tracked in git)
├── data/                         # Odoo filestore (gitignored)
├── logs/                         # Runtime logs (gitignored)
└── backup/                       # Backups (gitignored)

/home/odoo-19.git/                # Bare repo (push target)
└── hooks/
    └── post-receive              # Branch detection + deploy trigger

/var/log/odoo-19-deploy.log       # Deploy history
```
