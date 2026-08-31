# Deploying WaniaS2 BedTracker

Pick **one** of the three options below. All cost **$0**.

| | Runs where | Card needed? | Works when you're away? | HTTPS | Best for |
|---|---|---|---|---|---|
| **A. Render + Neon** | Render's servers | Card **on file** (not charged) | Yes, always | Yes | Proper cloud hosting |
| **B. Your PC + Tailscale Funnel** | Your Windows PC | **No** | Only while your PC is on + online | Yes | Truly card-free, reachable off-site |
| **C. Your PC on the hospital Wi-Fi** | Your Windows PC | **No** | Only on-site, PC on | No (LAN only) | Simplest, everyone's in the building |

The project is already prepared for all three (env-driven settings, WhiteNoise
static files, `waitress` for Windows, `gunicorn` for Linux, health check, PWA).

---

## Option A — Render + Neon (recommended if you can add any card)

Render now asks every new account to put a card **on file** (anti-abuse). The
**free tier is still $0** — free usage is never billed. A debit card works. You
can set the workspace **spend limit to $0** so it can never charge you.
Database is [Neon](https://neon.tech) (free Postgres, never expires, **no card**).

### A1. Code to GitHub
Create an empty repo at <https://github.com/new> named `wanias2-bedtracker`
(no README/licence). Then, in the project's PowerShell window:

```powershell
git remote add origin https://github.com/<your-username>/wanias2-bedtracker.git
git push -u origin main
```

### A2. Database on Neon
1. Sign up at <https://neon.tech> with GitHub (no card).
2. **Create project** → region **AWS ap-southeast-1 (Singapore)**, Postgres 16.
3. **Connection Details** → copy the **connection string**
   (`postgresql://…-pooler.…neon.tech/neondb?sslmode=require`). Keep it handy.

### A3. Web service on Render
1. Sign up at <https://render.com> with GitHub. Add a card if asked; then
   **Settings → Billing → set a spend limit of $0**.
2. **New + → Blueprint** → pick `wanias2-bedtracker` → **Apply**.
3. Enter the secrets it asks for (`DATABASE_URL` = the Neon string; the others
   are in the table below).
4. First deploy ≈ 3–5 min. Note the URL, e.g.
   **`https://wanias2-bedtracker.onrender.com`**.
5. In the service's **Environment** tab set `BEDTRACKER_ALLOWED_HOSTS` and
   `BEDTRACKER_CSRF_TRUSTED_ORIGINS` to that URL (table below) → **Manual Deploy**.

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon connection string |
| `BEDTRACKER_ALLOWED_HOSTS` | `wanias2-bedtracker.onrender.com` (host only) |
| `BEDTRACKER_CSRF_TRUSTED_ORIGINS` | `https://wanias2-bedtracker.onrender.com` |
| `BEDTRACKER_DEBUG`, `BEDTRACKER_SECRET_KEY`, `PYTHON_VERSION`, `WEB_CONCURRENCY` | *set automatically by `render.yaml` — leave them* |

### A4. Admin account
Render → your service → **Shell**:

```
python manage.py createsuperuser
python manage.py seed_demo      # optional: task categories + demo data
```

### A5. Updating later
`git add -A` → `git commit -m "…"` → `git push`. Render redeploys automatically;
`build.sh` runs `collectstatic` + `migrate` each time.

**Free-tier note:** the web service sleeps after 15 min of no traffic (~50 s to
wake). During a shift with people using it, it stays awake.

---

## Option B — Your Windows PC + Tailscale Funnel (no card, off-site access)

Your PC runs the app; Tailscale Funnel gives it a stable public HTTPS address
like `https://ward-pc.tailXXXX.ts.net`. Free, no card. Works only while your PC
is on and online. Database stays the local SQLite file (your backup system
already covers it).

### B1. One-time setup

1. **Install the app's server extras** (in the project's PowerShell):
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. **Install Tailscale**: <https://tailscale.com/download/windows> → sign in
   (Google/GitHub, free "Personal" plan, no card). This gives your PC a name.

3. **Enable HTTPS + Funnel** in the Tailscale admin console
   (<https://login.tailscale.com/admin/dns> → enable **MagicDNS** and
   **HTTPS Certificates**; <https://login.tailscale.com/admin/acls> is not
   needed for a personal tailnet — Funnel is allowed by default on Personal).

4. **Create `.env`** in the project folder (PowerShell):
   ```powershell
   @'
   BEDTRACKER_DEBUG=false
   BEDTRACKER_ALLOW_SQLITE=true
   BEDTRACKER_SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_STRING
   BEDTRACKER_ALLOWED_HOSTS=YOUR-PC-NAME.tailXXXX.ts.net
   BEDTRACKER_CSRF_TRUSTED_ORIGINS=https://YOUR-PC-NAME.tailXXXX.ts.net
   '@ | Set-Content -Encoding utf8 .env
   ```
   Generate the secret key with:
   ```powershell
   .\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
   ```
   Find `YOUR-PC-NAME.tailXXXX.ts.net` in the Tailscale admin console (Machines →
   your PC → the "…ts.net" name).

5. **Set up the database and admin** (one time):
   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate
   .\.venv\Scripts\python.exe manage.py collectstatic --no-input
   .\.venv\Scripts\python.exe manage.py createsuperuser
   .\.venv\Scripts\python.exe manage.py seed_demo
   ```

### B2. Each time you want it online

Two windows:

```powershell
# Window 1 - the app
.\.venv\Scripts\waitress-serve.exe --host=127.0.0.1 --port=8000 config.wsgi:application
```

```powershell
# Window 2 - expose it
tailscale funnel 8000
```

Users go to `https://YOUR-PC-NAME.tailXXXX.ts.net`. Close either window to take
it offline. (`tailscale funnel --bg 8000` keeps it running after you close the
window; `tailscale funnel off` stops it.)

### B3. Updating later
```powershell
git pull                                   # if you edit code elsewhere
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --no-input
```
then restart the two windows.

---

## Option C — Hospital Wi-Fi only (simplest)

Everyone using it is in the building on the same network.

```powershell
@'
BEDTRACKER_DEBUG=false
BEDTRACKER_ALLOW_SQLITE=true
BEDTRACKER_SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_STRING
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
private networks the first time. (No HTTPS on a plain LAN — fine inside the
hospital network; `*` in ALLOWED_HOSTS is acceptable because only your LAN can
reach the PC.)

---

## Backups (all options)

`backup/README.md` has the details.

- **Options B & C** (SQLite): nothing changes — the scheduled task already backs
  up `db.sqlite3`.
- **Option A** (Neon Postgres): set `backup/backup.env` to `DB_KIND=postgres`
  with Neon's **direct** (non-`-pooler`) host, `PG_SSLMODE=require`, and put the
  password only in `%APPDATA%\postgresql\pgpass.conf`. Install PostgreSQL
  "Command Line Tools" for `pg_dump`. See `backup/backup.env.example`.

Backups always land in `...\BedTracker\backup\`, never in Git, and run
independently of the web host.

---

## Custom domain later (any option)

Buy a domain, point it at the host (Render: add it in the dashboard, one DNS
record, free TLS cert — or Tailscale: `tailscale serve` with your own cert).
Then add the domain to `BEDTRACKER_ALLOWED_HOSTS` and
`BEDTRACKER_CSRF_TRUSTED_ORIGINS`. **No code change.**
