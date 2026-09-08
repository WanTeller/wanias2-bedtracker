# Deploying WaniaS2 BedTracker

Every option below costs **$0**. Pick one.

| | Runs on | Card? | Reachable when you're away | Stays awake | Notes |
|---|---|---|---|---|---|
| **A. PythonAnywhere** *(recommended)* | PythonAnywhere's computers | **No** | Yes | Yes | **Permanent $0.** Click a keep-alive link they email ~every 3 months. Best all-round choice. |
| **B. Railway + Neon** | Railway's cloud | **No** (trial) | Yes | Yes | 30-day trial = full hosting; then ~$1/mo credit ≈ a few days/mo. A short pilot only. |
| **C. Your PC + Tailscale Funnel** | Your Windows PC | **No** | Only while your PC is on + online | — | Permanent $0. Public URL. You keep two windows open. |
| **D. Your PC on hospital Wi-Fi** | Your Windows PC | **No** | On-site only, PC on | — | Simplest, but on-site only. |
| *(E. Render + Neon)* | Render's cloud | Card **on file**, not charged | Yes | No (sleeps ~15 min idle) | Only if a debit card on file is OK. `render.yaml` is included; steps mirror B at render.com. |

The repo is already set up for all of them (`railway.json`, `render.yaml`,
`build.sh`, `Procfile`, static-file serving built in, `waitress` for Windows,
a `/healthz/` check, installable-app support).

Because the board holds no confidential data, Options A, C and D use the app's
simple built-in storage (a single file) and the **name-only login**
(`BEDTRACKER_SIMPLE_LOGIN=true`). Options B and E use a managed database.

## Multiple boards & how many people

The app is multi-board: after signing in with a name, each person lands on
**"Your boards"**. Anyone can **Create a board** (a name + a bed count); it gets
a **share link** (in the board's ☰ menu → "Share this board"). People with that
link join that board; boards are otherwise invisible to each other. The board's
creator is its **owner** (can reset the share link and clear the board's data).

Scale for the pilot: the single-file storage (Options A/C/D) comfortably
handles the ~15-25 people active on a board at once. Across many boards and
~100+ signed-up people it should still be fine for a feedback pilot, because
writes are short and rarely simultaneous. If boards feel sluggish under load,
move to **Option B** (a managed database) — no data is lost in the move.

Name-only login means two people typing the same first name share one identity
in the activity log; the name box suggests "Firstname L." to reduce clashes.
Switch to email logins (`BEDTRACKER_SIMPLE_LOGIN=false`) when that matters.

---

## Option A — PythonAnywhere (recommended: permanent $0, no card)

PythonAnywhere runs your app on their computers, free, with no credit card and no
deadline. Your app gets an address like
`https://waniabedtracker.pythonanywhere.com`. It stays awake — no "waking up"
delay when someone opens it. The only upkeep: roughly every three months they
email you a link to click that keeps the free app running (5 seconds).

Set aside about an hour the first time. You'll make an account, copy the code
onto their system with a few pasted commands, fill in one settings file, and
click through their "Web" setup page.

### A1. Put the code on GitHub (skip if you've already done this)

Create an empty repository at <https://github.com/new> called
`wanias2-bedtracker` (no README, no licence). Then, in the project's PowerShell
window:

```powershell
git remote add origin https://github.com/<your-username>/wanias2-bedtracker.git
git push -u origin main
```

### A2. Make a PythonAnywhere account

1. Go to <https://www.pythonanywhere.com/registration/register/beginner/> and
   sign up for the free **"Beginner"** account. No card.
2. Choose a username you're happy to see in the web address — it becomes
   `https://<username>.pythonanywhere.com`. The examples below use
   `waniabedtracker`; substitute your own everywhere you see it.

### A3. Download the code onto PythonAnywhere

1. On the dashboard open the **Consoles** tab → click **Bash**. A black terminal
   opens in your browser.
2. Type each line below, pressing Enter after each. Replace `<your-username>`
   with your **GitHub** username in the first line.

```bash
git clone https://github.com/<your-username>/wanias2-bedtracker.git
```

```bash
cd wanias2-bedtracker
```

```bash
mkvirtualenv --python=/usr/bin/python3.11 bedtracker
```

```bash
pip install -r requirements.txt
```

The last one takes a couple of minutes. When it finishes you'll see the prompt
again with `(bedtracker)` at the start of the line — that means the app's
toolbox is active.

### A4. Create the settings file

1. In the same Bash console, make a secret key:

   ```bash
   python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
   ```

   Select the line it prints and copy it.

2. Open the **Files** tab. Click into the `wanias2-bedtracker` folder. In the
   **"Enter new file name"** box type `.env` and click **New file**.
3. In the editor that opens, paste this exactly, then change the two marked
   lines:

   ```
   BEDTRACKER_DEBUG=false
   BEDTRACKER_ALLOW_SQLITE=true
   BEDTRACKER_SIMPLE_LOGIN=true
   BEDTRACKER_SECRET_KEY=paste-the-key-you-copied-here
   BEDTRACKER_ALLOWED_HOSTS=waniabedtracker.pythonanywhere.com
   ```

   - `BEDTRACKER_SECRET_KEY=` — replace everything after the `=` with the key
     you copied.
   - `BEDTRACKER_ALLOWED_HOSTS=` — replace `waniabedtracker` with your username.

4. Click **Save**.

(To switch to real email + password logins later: change
`BEDTRACKER_SIMPLE_LOGIN` to `false`, Save, then Reload the app — step A7.)

### A5. Set up the board's data and your admin account

Back in the Bash console (Consoles tab). If you opened a fresh one, first run
`workon bedtracker` and `cd ~/wanias2-bedtracker`. Then, one line at a time:

```bash
python manage.py migrate
```

```bash
python manage.py collectstatic --no-input
```

```bash
python manage.py seed_demo
```

`seed_demo` fills the board with the ward, 44 beds and a few sample patients so
it isn't empty. To start completely blank instead, run
`python manage.py seed_categories` in place of `seed_demo` (that only sets up the
task buttons).

Make yourself a developer account for the `/admin/` page:

```bash
python manage.py createsuperuser
```

It asks for an email and a password. The password stays invisible as you type —
that's normal.

### A6. Turn the website on

1. Open the **Web** tab → **Add a new web app** → **Next**.
2. Choose **Manual configuration** (*not* the "Django" option) → pick
   **Python 3.11** → **Next**.
3. You're now on the web app's settings page. Set three things:

   - **Source code:** click the value and enter
     `/home/<username>/wanias2-bedtracker`
   - **Virtualenv:** in the "Virtualenv" section, enter `bedtracker` and confirm
     — it fills in the full path itself.
   - **WSGI configuration file:** click the blue link near the top (it looks
     like `/var/www/<username>_pythonanywhere_com_wsgi.py`). An editor opens.
     **Delete everything in it** and paste the following, replacing `<username>`:

     ```python
     import os
     import sys

     path = "/home/<username>/wanias2-bedtracker"
     if path not in sys.path:
         sys.path.insert(0, path)

     os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

     from django.core.wsgi import get_wsgi_application
     application = get_wsgi_application()
     ```

     Click **Save**.

4. Back on the **Web** tab, scroll to **Security** and turn **Force HTTPS** on.
5. Click the big green **Reload** button at the top.

Open `https://<username>.pythonanywhere.com` — you should see the login page.
Type any name and you're on the board. Send that address to the team; on each
phone they open it once and choose **"Add to Home Screen"** to get an app icon.

### A7. Keeping it running, and making changes later

- **Keep-alive:** PythonAnywhere emails you about every 3 months saying the free
  web app will be disabled unless you click a link. Click it — done. If you miss
  it the app just pauses (nothing is deleted); click the link and press
  **Reload** to bring it back.
- **After you change the code** (on your PC: `git add -A`, `git commit`,
  `git push`), update the live site: open a Bash console and run

  ```bash
  cd ~/wanias2-bedtracker && workon bedtracker && git pull && pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --no-input
  ```

  then go to the **Web** tab and click **Reload**.

### A8. Backups

The entire board is one file:
`/home/<username>/wanias2-bedtracker/db.sqlite3`.

- **By hand:** Files tab → open the `wanias2-bedtracker` folder → click the
  download arrow next to `db.sqlite3`. Do this weekly and keep the copies
  somewhere safe.
- **Automatic:** the free plan includes one daily scheduled task. Tasks tab →
  add a daily task with this command:

  ```bash
  cp ~/wanias2-bedtracker/db.sqlite3 ~/db-backup-$(date +%Y%m%d).sqlite3
  ```

  It leaves a dated copy in your home folder each day; download and tidy them
  from the Files tab now and then.

Your existing Windows backup system is for the self-hosted options (C/D) and
isn't needed here.

---

## Option B — Railway + Neon (card-free cloud, but only free for ~30 days)

Use this for a **short pilot**. Railway hosts the app; Neon hosts a proper
database. No card to start, but the free credit runs out in about a month.

### B1. Code to GitHub

Same as A1 above.

### B2. Database on Neon (free database, no card, never expires)

1. Sign up at <https://neon.tech> with GitHub.
2. **Create project** → region **AWS ap-southeast-1 (Singapore)**, Postgres 16.
3. Open **Connection Details** → copy the **connection string**
   (`postgresql://…-pooler.…neon.tech/neondb?sslmode=require`).

### B3. Web service on Railway

1. Sign up at <https://railway.com> with GitHub. Choose **"Start a New Project"**
   → **"Deploy from GitHub repo"** → pick `wanias2-bedtracker`.
   The $5 trial starts with **no credit card**.
2. Railway reads `railway.json`, installs the packages, runs `bash build.sh`, and
   starts the app. First build ≈ 2–4 min.
3. Service → **Settings → Networking → Generate Domain** → you get a URL like
   **`https://web-production-xxxx.up.railway.app`**.
4. Service → **Variables** tab → add these. The admin account and demo data are
   created automatically on the next build (Railway's "Console" shell can't run
   `manage.py`, so the build does it):

   | Variable | Value |
   |---|---|
   | `BEDTRACKER_DEBUG` | `false` |
   | `BEDTRACKER_SIMPLE_LOGIN` | `true` (name-only login) |
   | `BEDTRACKER_SECRET_KEY` | a long random string *(generate: B5)* |
   | `DATABASE_URL` | the Neon connection string from B2 |
   | `DJANGO_SUPERUSER_USERNAME` | your email |
   | `DJANGO_SUPERUSER_EMAIL` | your email (same) |
   | `DJANGO_SUPERUSER_PASSWORD` | a password for the admin account |
   | `BEDTRACKER_SEED_DEMO` | `true` |

5. Railway redeploys automatically. Watch **Deployments → View logs** until
   "Deployment successful".
6. **After that first good deploy, delete `DJANGO_SUPERUSER_PASSWORD`** (and
   optionally the other `DJANGO_SUPERUSER_*` and `BEDTRACKER_SEED_DEMO`) so the
   password isn't sitting in the list. The account stays.

### B4. Log in

Open your Railway URL. With `BEDTRACKER_SIMPLE_LOGIN=true` you just enter a name.
`/admin/` on that URL is your developer console (superuser email + password).

### B5. Generate a secret key

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

### B6. Updating later

`git add -A` → `git commit -m "…"` → `git push`. Railway redeploys automatically.

**Trial limit:** after 30 days Railway's Free plan gives ~$1/month of credit,
which keeps a small service up only a few days a month. Before then, decide: pay
Railway's Hobby plan (~$5/mo, no sleep) **or** move to Option A (PythonAnywhere)
or Option C (self-host). Your data lives in Neon and can move with you.

---

## Option C — Your Windows PC + Tailscale Funnel (permanent $0, no card)

Your PC runs the app; [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)
gives it a stable public HTTPS URL like `https://ward-pc.tailXXXX.ts.net`. Free,
no card. Works only while your PC is on and online. The board stays the local
file (`db.sqlite3`); your Windows backup system already covers it.

### C1. One-time setup

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
BEDTRACKER_SIMPLE_LOGIN=true
BEDTRACKER_SECRET_KEY=PASTE_A_LONG_RANDOM_STRING
BEDTRACKER_ALLOWED_HOSTS=YOUR-PC-NAME.tailXXXX.ts.net
BEDTRACKER_CSRF_TRUSTED_ORIGINS=https://YOUR-PC-NAME.tailXXXX.ts.net
'@ | Set-Content -Encoding utf8 .env
```

(Generate the key with the command in B5. Find `YOUR-PC-NAME.tailXXXX.ts.net` in
the Tailscale admin console → Machines → your PC.)

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --no-input
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
```

### C2. Each time you want it online (two PowerShell windows)

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

### C3. Updating later

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --no-input
```

then restart the two windows.

---

## Option D — Hospital Wi-Fi only

Everyone using it is in the building on the same network.

```powershell
@'
BEDTRACKER_DEBUG=false
BEDTRACKER_ALLOW_SQLITE=true
BEDTRACKER_SIMPLE_LOGIN=true
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

- **Option A** (PythonAnywhere): see step A8 — download `db.sqlite3` from the
  Files tab, or use the one free daily scheduled task.
- **Options C & D** (SQLite on your PC): nothing changes — the scheduled task
  already backs up `db.sqlite3`.
- **Options B & E** (Neon database): set `backup/backup.env` to
  `DB_KIND=postgres` with Neon's **direct** (non-`-pooler`) host,
  `PG_SSLMODE=require`, password only in `%APPDATA%\postgresql\pgpass.conf`.
  Install PostgreSQL "Command Line Tools" for `pg_dump`. See
  `backup/backup.env.example`.

Backups never go into Git and never depend on the web host.

---

## Custom domain later (any option)

Point a domain at the host (Railway/Render: add it in the dashboard, one DNS
record, free certificate; PythonAnywhere: a paid plan is needed for a custom
domain). Add the domain to `BEDTRACKER_ALLOWED_HOSTS` and
`BEDTRACKER_CSRF_TRUSTED_ORIGINS`. **No code change.**
