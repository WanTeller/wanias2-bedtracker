# Ward Board

A hospital ward task board, rebuilt in Python from a Base44 prototype.
Stack: **Django + SQLite (PostgreSQL-ready) + Django templates + HTMX + CSS**.

See [CLAUDE.md](CLAUDE.md) for the full project context and feature plan.
**New to this / just running the testing phase?** Follow
[HOW-TO-RUN.md](HOW-TO-RUN.md) instead — it assumes no programming experience.

## Project layout

| Path | What it is |
|------|-----------|
| `config/settings.py` | All configuration; reads secrets from env / `.env` |
| `board/` | The ward board app (models, views, services, templates) |
| `accounts/` | Login / signup / password reset + the login registry |
| `backup/` | Independent local database-backup system — see `backup/README.md` |
| `templates/` , `static/` | HTML pages and CSS/JS (HTMX is vendored) |
| `db.sqlite3` | The database file (created locally, git-ignored) |
| `.env` | Local secrets (git-ignored; optional in dev) |
| `_archive_flask/` | The throwaway Flask v1 from early exploration — ignore |

## One-time setup (Windows PowerShell, run in the project folder)

```bash
python -m venv .venv
```

```bash
.venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
```

```bash
python manage.py migrate
```

Creates the database tables.

```bash
python manage.py seed_demo
```

Adds the task categories, a sample ward, 44 beds, 6 invented patients and some
sample tasks. (`python manage.py seed_categories` on its own just
creates/updates the categories and their preset buttons.)

```bash
python manage.py createsuperuser
```

**Do this.** The superuser is you, the developer/administrator — it's the only
account that can open `/admin/` (the user registry, login history, and the
activity log with "who did what"). Username = your email address.

`python manage.py seed_demo` also creates a normal demo login:
`demo@ward.local` / `demo-pass-1234`.

Other users create their own accounts at `/accounts/signup/` (name + email +
password). One email = one account.

### Testing mode (name-only login)

Set `BEDTRACKER_SIMPLE_LOGIN=true` (in a `.env` file or the environment) and the
login page asks only for a name — click **Enter Ward Board** and you're in, no
signup. Each browser keeps its own name; that name is what shows in the activity
log. Set it back to `false` (or remove it) to restore the real email/password
flow — existing accounts and data are untouched. `.env.example` documents this
and every other setting.

The sidebar's developer "Clear all patient data" button uses a password
(`BEDTRACKER_DEV_CLEAR_PASSWORD`, default `clear-ward`; set it empty to hide).

## Running it

```bash
python manage.py runserver
```

Open <http://localhost:8000> (it will send you to the login page). Stop with
`Ctrl + C`. Admin site: <http://localhost:8000/admin/>.

## Local backups

Automatic, Anki-style, independent of the web app. One-time setup on your
Windows PC:

```powershell
cd backup
powershell -ExecutionPolicy Bypass -File .\register_backup_task.ps1
```

Full instructions, verification and restore steps: [backup/README.md](backup/README.md).

To reset the sample data at any time:

```bash
python manage.py seed_demo --reset
```

## Roadmap

- [x] **Phase 1** — Django skeleton; ward with 44 beds; click a bed → Patient
  panel → enter details → Save → bed becomes occupied; occupied beds sort first.
- [x] **Phase 2** — Discharge (two-step confirm), activity-log events on
  admit/discharge, per-patient History tab, Ward Activity sidebar
  (Activity / Discharged / Tomorrow).
- [x] **Phase 3** — Tasks tab: category slots (collapsible, active-first,
  Order/Chase Labs paired), preset + custom tasks, per-category overdue timing,
  task-driven bed colour, live Pending/Overdue counts, filter chips, per-slot
  tick, edit/reschedule/cancel. HTMX for in-place updates.
- [x] **Phase 4** — Notes tab (free-text notes), Vitals tab (BP/HR/temp/… with
  a history table), sidebar "Tomorrow" list (tasks due tomorrow, with a count).
- [x] **Phase 5** — search (patients / tasks / notes), developer "clear all
  data" control in the sidebar (password-gated), styling pass + panel animation.
- [x] **Auth / concurrency / backups** — email+password login, developer-only
  user & login registry in `/admin/`, optimistic-locking + DB constraints +
  row locking for safe simultaneous use, "who did it" on every activity event,
  and an independent local backup system (`backup/`).
- [ ] **Later** — deploy to a free-tier host + PostgreSQL (see the end of
  CLAUDE.md); optional Google sign-in; hospital-system lab integration.
