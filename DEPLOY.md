# Deploying WaniaS2 BedTracker

All options below cost **$0**. Pick one.

| | Runs on | Card? | Reachable when you're away | HTTPS | Notes |
|---|---|---|---|---|---|
| **A. Railway + Neon** | Railway's cloud | **No** (trial) | Yes | Yes | 30-day trial = full hosting; then ~$1/mo credit ≈ a few days/mo. Best for a **pilot**. |
| **B. Your PC + Tailscale Funnel** | Your Windows PC | **No** | Only while your PC is on + online | Yes | **Permanent $0.** Public URL. |
| **C. Your PC on hospital Wi-Fi** | Your Windows PC | **No** | On-site only, PC on | No (LAN) | Simplest. |
| *(D. Render + Neon)* | Render's cloud | Card **on file**, not charged | Yes | Yes | Only if a debit card on file is OK. Same steps as A but at render.com; `render.yaml` is included. |

The repo is already configured for all of them (`railway.json`, `render.yaml`,
`build.sh`, `Procfile`, WhiteNoise static, `waitress` for Windows, `/healthz/`,
PWA). Railway/Render auto-fill the app's own hostname, so you don't set
`BEDTRACKER_ALLOWED_HOSTS` there.

---

## Option A — Railway + Neon (card-free cloud pilot)

### A1. Code to GitHub
Create an empty repo at <https://github.com/new> named `wanias2-bedtracker`
(no README/licence). Then in the project's PowerShell window:

```powershell
git remote add origin https://github.com/<your-username>/wanias2-bedtracker.git
git push -u origin main
```

### A2. Database on Neon (free Postgres, no card, never expires)
1. Sign up at <https://neon.tech> with GitHub.
2. **Create project** → region **AWS ap-southeast-1 (Singapore)**, Postgres 16.
3. Open **Connection Details** → copy the **connection string**
   (`postgresql://…-pooler.…neon.tech/neondb?sslmode=require`).

### A3. Web service on Railway
1. Sign up at <https://railway.com> with GitHub. Choose **"Start a New Project"**
   → **"Deploy from GitHub repo"** → pick `wanias2-bedtracker`.
   The $5 trial starts with **no credit card**.
2. Railway reads `railway.json`, installs the packages, runs `./build.sh`, and
   starts `gunicorn`. First build ≈ 2–4 min.
3. Open the service → **Variables** tab → add:

   | Variable | Value |
   |---|---|
   | `BEDTRACKER_DEBUG` | `false` |
   | `BEDTRACKER_SECRET_KEY` | a long random string *(generate: see A5)* |
   | `DATABASE_URL` | the Neon connection string from A2 |

4. Service → **Settings → Networking → Generate Domain**. You get a URL like
   **`https://wanias2-bedtracker-production.up.railway.app`**.
5. Railway redeploys automatically after the variable changes. The first build
   (before you added the variables) ran on a throwaway database; this redeploy
   uses Neon.

### A4. Admin account
Railway service → the **⋮ menu → "Terminal"** (or install the Railway CLI and
`railway run`), then:

```
python manage.py createsuperuser
python manage.py seed_demo      # optional: task categories + demo data
```

Log in at `https://<your-url>/admin/`.

### A5. Generate a secret key

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

### A6. Updating later
`git add -A` → `git commit -m "…"` → `git push`. Railway redeploys automatically;
`build.sh` runs `collectstatic` + `migrate` each time.

**Trial limit:** after 30 days Railway's Free plan gives ~$1/month of credit,
which keeps a small service up for only a few days a month. Before then, decide:
pay Railway's Hobby plan (~$5/mo, no sleep) **or** switch to Option B.

---

## Option B — Your Windows PC + Tailscale Funnel (permanent $0, no card)

Your PC runs the app; [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)
gives it a stable public HTTPS URL like `https://ward-pc.tailXXXX.ts.net`. Free,
no card, [no bandwidth or connection limits](https://dev.to/recca0120/cloudflare-tunnel-in-2026-expose-localhost-without-opening-ports-or-buying-an-ip-32l5).
Works only while your PC is on and online. Database stays the local SQLite file
(your backup system already covers it).

### B1. One-time setup
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
Install Tailscale: <https://tailscale.com/download/windows> → sign in
(Google/GitHub, free "Personal" plan, no card). In the Tailscale admin console
enable **MagicDNS** and **HTTPS Certificates**
(<https://login.tailscale.com/admin/dns>).

Create `.env` in the project folder (replace the two placeholders):
```powershell
@'
BEDTRACKER_DEBUG=false
BEDTRACKER_ALLOW_SQLITE=true
BEDTRACKER_SECRET_KEY=PASTE_A_LONG_RANDOM_STRING
BEDTRACKER_ALLOWED_HOSTS=YOUR-PC-NAME.tailXXXX.ts.net
BEDTRACKER_CSRF_TRUSTED_ORIGINS=https://YOUR-PC-NAME.tailXXXX.ts.net
'@ | Set-Content -Encoding utf8 .env
```
(Generate the key with the command in A5. Find `YOUR-PC-NAME.tailXXXX.ts.net` in
the Tailscale admin console → Machines → your PC.)

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --no-input
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
```

### B2. Each time you want it online (two PowerShell windows)
```powershell
# Window 1 - the app
.\.venv\Scripts\waitress-serve.exe --host=127.0.0.1 --port=8000 config.wsgi:application
```
```powershell
# Window 2 - expose it
tailscale funnel 8000
```
Users go to `https://YOUR-PC-NAME.tailXXXX.ts.net`.
(`tailscale funnel --bg 8000` keeps it up after closing the window;
`tailscale funnel off` stops it.)

### B3. Updating later
```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --no-input
```
then restart the two windows.

---

## Option C — Hospital Wi-Fi only

Everyone using it is in the building on the same network.

```powershell
@'
BEDTRACKER_DEBUG=false
BEDTRACKER_ALLOW_SQLITE=true
BEDTRACKER_SECRET_KEY=PASTE_A_LONG_RANDOM_STRING
BEDTRACKER_ALLOWED_HOSTS=*
BEDTRACKER_SSL_REDIRECT=false
'@ | Set-Content -Encoding utf8 .env

.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --no-input
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\waitress-serve.exe --host=0.0.0.0 --port=8000 config.wsgi:application
```

Find your PC's address with `ipconfig` (IPv4 Address, e.g. `192.168.1.20`).
Users open `http://192.168.1.20:8000`. Allow the Windows Firewall prompt for
private networks the first time.

---

## Backups (every option)

- **Options B & C** (SQLite): nothing changes — the scheduled task already backs
  up `db.sqlite3`.
- **Options A & D** (Neon Postgres): set `backup/backup.env` to
  `DB_KIND=postgres` with Neon's **direct** (non-`-pooler`) host,
  `PG_SSLMODE=require`, password only in `%APPDATA%\postgresql\pgpass.conf`.
  Install PostgreSQL "Command Line Tools" for `pg_dump`. See
  `backup/backup.env.example`.

Backups always land in `...\BedTracker\backup\`, never in Git, independent of
the web host.

---

## Custom domain later (any option)

Point a domain at the host (Railway/Render: add it in the dashboard, one DNS
record, free TLS cert). Add the domain to `BEDTRACKER_ALLOWED_HOSTS` and
`BEDTRACKER_CSRF_TRUSTED_ORIGINS`. **No code change.**
