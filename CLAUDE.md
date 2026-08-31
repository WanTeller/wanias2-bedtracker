# Ward Bed Tracker — Project Context

## Background
I'm a surgical intern. My ward has around 44 beds, and keeping track of each
bed/patient throughout the day gets haphazard. I currently struggle to track:
- whether lab results are back
- whether labs have been chased
- what orders the resident gave (these come in throughout the day and
  sometimes get missed or lost in translation)
- which of my own tasks as intern are done vs pending

Frequent recurring tasks include: IV hydration, arranging blood, labs,
reviews, referrals, assessments.

I originally built a version of this as a low-code app on Base44, styled
like a Western-care EMR/bed-board interface. I'm now replicating it in
Python from scratch, with your help, as a complete beginner to coding.

Eventually I'd like this to be a shared board the whole team (including
residents) can use, and ideally linked to the hospital's system so lab
results transfer in automatically — but that's a later-stage goal, not
part of the first working version.

## Core features (target feature set)

**Per-bed view should show:**
- Basic patient history, chief complaint
- Active plans
- Last vitals / BP
- Last labs chased
- Pending orders
- Received results

**Bed list behavior:**
- Beds grouped occupied-first, then unoccupied
- Numerically ordered within each group
- This ordering applies across every slot/tab, not just the main view

**Bed status / color logic:**
- Bed color/status tied to how old a task is (i.e. overdue tasks should
  visually stand out)

**Task subpanels:**
- Task categories include things like Hydration, Medication, GA Fitness,
  etc., each with their own subpanel
- Subpanels should support a custom "add" option for tasks not in the
  preset list
- Sub-panel dropdowns should be closed by default, only opening on click
- Order Labs and Chase Labs should be separate slots but always displayed
  side by side
- Receiving Notes should be its own listed task, not just a note field
- Manual "add task" for anything not prelisted should go into an
  "Unassigned" category
- Each task needs cancel / edit / reschedule interactions
- Per-task pending counters
- Active tasks/slots should be prioritized above passive ones (same
  ordering principle as the bed list)

**Filter tabs:** All / Pending / Overdue / Unassigned

**Bed panel behavior:**
- Show patient data before tasks
- For an empty/unassigned bed: default open tab is "Patient", and patient
  data (specifically: **patient name only** — all other fields optional)
  is required before the bed can be marked occupied
- For an already-assigned bed: default open tab is "Tasks"
- Overall tick/untick per slot, separate from individual sub-panel
  checkboxes
- No "clear patient data" control on the bed panel itself (see sidebar
  below)

**Sidebar (history / admin panel):**
- Activity log
- Discharged patients
- Tasks for tomorrow (with a numbering counter)
- Developer-only "clear all patient data" control, gated behind my own
  Google sign-in — this should live ONLY in the sidebar, not the bed panel

## Known bugs to avoid re-introducing
- Beds whose only pending task is "Chase Labs" incorrectly showing up
  under "Unassigned" instead of the Chase Labs slot — Chase Labs must be
  recognized as an assigned/active task type.

## How I'd like you to work with me
- I am completely new to coding and Python. Explain briefly what each
  piece of code does as you go, in plain language.
- Build incrementally — start with the simplest possible working version
  (e.g. one bed, patient name, save/load), confirm it runs, then add
  features one at a time in the order above.
- Prefer simple, common tools over anything exotic, since I'll need to
  understand and maintain this. (Stack chosen: Django + SQLite + Django
  templates + CSS, with HTMX later. Decided 2026-08-30 — supersedes the
  earlier "Flask or FastAPI" note here, because the app is heading toward
  multi-user sharing + hospital-system links, where Django's built-in admin,
  auth and migrations save us the most hand-written code.)
- After significant changes, update this CLAUDE.md file to reflect the
  current state of the project so future sessions stay in sync.

## Current implementation status

**Phases 1–5 + auth/concurrency/backups complete (2026-08-31).** The prototype
rebuild is done. Remaining work is hosting (see the end of this file).

Structure:
- Django project `config/`, apps `board/` (the ward board) and `accounts/`
  (login / signup / user + login registry).
- JavaScript: HTMX only (`static/htmx.min.js`, v2.0.4, vendored - loaded in
  `templates/base.html`, which also sends the CSRF token via `hx-headers`).
  Plus `?v=N` on `board.css` in base.html - bump N whenever you edit the CSS.
- **Config & secrets**: `config/settings.py` reads everything sensitive from the
  environment (or a git-ignored `.env` in the project root, loaded by a tiny
  built-in parser). `BEDTRACKER_SECRET_KEY`, `BEDTRACKER_DEBUG`,
  `BEDTRACKER_ALLOWED_HOSTS`, `BEDTRACKER_DB` (`sqlite`|`postgres`) +
  `BEDTRACKER_DB_*`, `BEDTRACKER_EMAIL_*`, `BEDTRACKER_DEV_CLEAR_PASSWORD`,
  `BEDTRACKER_SQLITE_PATH` (for test-restores).
- **Login required for everything** via Django 5.1's `LoginRequiredMiddleware`.
  Only `accounts.views.signup` is `@login_not_required` (Django exempts its own
  auth views + admin login automatically).
- `python manage.py seed_demo [--reset]` - ward, 44 beds, sample patients/tasks,
  and a demo login `demo@ward.local` / `demo-pass-1234`.
- `python manage.py seed_categories` - 13 categories + preset buttons.
- `python manage.py test` - 42 tests.
- **Testing mode**: set `BEDTRACKER_SIMPLE_LOGIN=true` (env or `.env`) for
  name-only login. See the "Testing mode" section below. `.env.example` lists
  every `BEDTRACKER_*` var.
- SQLite runs in WAL mode with a 20s busy timeout (`config/settings.py`) so
  concurrent writers wait rather than erroring.

Models (`board/models.py`):
- `Ward`, `Bed`, `Patient`, `ActivityEvent`, `TaskCategory`, `TaskOption`,
  `Task`, `Note`, `VitalsEntry`.
- Bed occupancy is derived: `Bed.current_patient` = the active patient on that
  bed. Discharge keeps `patient.bed` for history.
- `Bed.attention` -> "overdue" / "pending" / "clear" / "empty" drives the bed
  card colour. Based on `Patient.has_overdue` / `has_pending`.
- `Task`: status open/done/cancelled. `Task.effective_due` = `due_at` or
  `created_at + category.overdue_after_minutes`. `is_overdue` = open & past due.
- `TaskCategory.pair_group` ("labs") = draw side by side (Order/Chase Labs).
  `overdue_after_minutes` per category. `allow_custom` shows the add box.
- Checkbox convention (from the prototype): **a ticked box = still to do**,
  untick = done. New tasks render ticked. `task.status` OPEN <-> `checked`.
- The slot master checkbox is derived (no model): ticked while the slot has
  open tasks. Unticking completes them all; re-ticking reopens them all; on an
  empty single-item slot (Receiving Notes) ticking creates the one task
  (`services.toggle_slot`).
- `ActivityEvent.kind` ∈ {admitted, discharged, ordered, completed, reopened,
  edited, cancelled, note, vitals, cleared_all}.
- `ActivityEvent.actor` (FK to User, SET_NULL) + `actor_name` (snapshot) record
  **who** did each thing. Every `board/services.py` function that writes an
  event takes `actor=` (the request user); views pass `request.user`.
- Data changes + event writing go through `board/services.py`
  (`add_task`, `complete_task`, `reopen_task`, `cancel_task`, `edit_task`,
  `toggle_slot`, `record_admission`, `record_discharge`, `add_note`,
  `add_vitals`, `clear_all_patient_data`).

### Concurrency safety (~15-20 simultaneous users)
- `Patient` has a partial `UniqueConstraint` (`bed`, `status='active'`) - the DB
  refuses a second active patient on one bed, so racing admissions can't both
  win. `save_patient` catches the `IntegrityError`.
- `save_patient` does an **optimistic-lock check**: the form carries the
  patient's `updated_at`; if it no longer matches, the save is refused with a
  message rather than silently overwriting another user's edit.
- `task_toggle` / `task_cancel` / `task_edit` run inside
  `transaction.atomic()` + `select_for_update()` on the task row, so concurrent
  actions on the same task serialise instead of double-firing.
- The task checkbox sends `hx-vals={"was": <status>}`; `task_toggle` ignores the
  click if the task's real status has changed since the page rendered (stops a
  stale page from un-completing someone else's work).
- All HTMX write forms carry `patient_id` (inherited via `hx-vals` on
  `.panel-body`); the view rejects the action if the bed's patient changed.
- `services.add_task` collapses an identical open task added within 6 seconds
  (accidental double-click / double-submit); add buttons also use
  `hx-disabled-elt`.
- Every task-action view is `@require_POST`.

Screens:
- Board `/`: top bar (hamburger → activity sidebar), 3 summary cards
  (Beds, Pending, Overdue - all live), a search box, filter chips, bed list.
  `?filter=all|pending|overdue|cat:<key>` narrows the bed list; chip counts =
  open task counts. Beds sorted occupied-first then empty, numeric.
- Search `/?q=<term>` (`_search` in views, `_search_results.html`): matches
  current patients (name/record/complaint/history/plan), their non-cancelled
  tasks, and their notes. While searching, the chips + bed list are replaced
  by grouped result rows that link to the right bed + tab.
- Slot order on the Tasks tab is FIXED by `category.sort_order` (Order/Chase
  Labs, Hydration, Medication, Radiology, Histopath, Referral, Review, Arrange
  Blood, GA Fitness, Vitals, Receiving Notes) with **Unassigned always last**
  (pinned in `_build_slot_rows`). No activity-based reordering.
- Bed panel `/?bed=<id>&tab=patient|tasks|notes|vitals|history`:
  - Tab default: an EMPTY bed opens on Patient and locks every other tab
    (rendered as disabled `<span>`) until a name is saved; an OCCUPIED bed
    opens on Tasks. `save_patient` redirects back to `&tab=patient` so the
    user can keep filling details right after admitting.
  - Patient tab = full form (only `name` required), Save, two-step inline
    Discharge confirm.
  - Tasks tab = category "slots" as `<details>` (collapsed by default; rows
    with open tasks sort to the top; Order/Chase Labs paired). Each slot:
    preset buttons, one "+ Add custom option" box, a slot-tick, and task rows
    (checkbox / edit-reschedule / cancel). Clicking a preset adds the task;
    "+ Add custom option" registers a reusable button AND adds the task.
    Permanent presets (from `seed_categories`, `is_custom=False`) have no ×;
    user-added ones (`is_custom=True`) have a × to remove them.
    Top "+ Add Task" (a `<details>`) files free text into Unassigned.
    "Unassigned" renders always-open; "Receiving Notes" renders as a flat row
    (no presets, no custom box).
  - Completing an "Order Labs" task auto-creates the matching "Chase Labs"
    task (`services._autolink_order_to_chase`).
  - Notes tab = free-text clinical notes, newest first, HTMX add
    (`_notes.html`, `#notes-panel`). Each note writes a `note` event.
  - Vitals tab = a `VitalsForm` (BP / HR / temp / RR / SpO2 / RBS / note,
    all optional, time defaults to now) + a history table, HTMX add
    (`_vitals.html`, `#vitals-panel`). Each set writes a `vitals` event.
  - History tab = that patient's events by day (now includes note/vitals).
  - Orders tab still disabled.
- Activity sidebar `/activity/?tab=activity|discharged|tomorrow`:
  - Tomorrow = open tasks whose `effective_due` date is tomorrow, numbered,
    grouped by bed, with a count badge on the tab. Each row links to that
    bed's Tasks. Set a due time via the task's pencil to schedule one here.
  - A `<details>` "⚙ Developer" section at the bottom (only when
    `settings.DEV_CLEAR_PASSWORD` is set) — password + "Clear all patient
    data" → `dev_clear` view → `services.clear_all_patient_data()` wipes
    patients/tasks/notes/vitals/events, keeps beds + task catalogue.

HTMX mechanics (Phase 3):
- Every task action posts and swaps `#tasks-panel` with `_tasks.html`, and the
  reply also carries out-of-band (`hx-swap-oob`) refreshes of `#summary`,
  `#chips` and that bed's `#bed-card-<id>`. See `board/_tasks_response.html`.
- `_render_task_action` in views returns the fragment for HTMX requests, or a
  plain redirect to the board if JS is off.
- After an action the acted-on slot re-renders `open` (`open_key`); other
  slots' expand state is client-side only and can reset - acceptable for now.

Django gotcha to remember: `{# ... #}` comments are SINGLE LINE only. Use
`{% comment %}...{% endcomment %}` for multi-line or it renders as text.

The 13 categories + their permanent preset buttons come from the Base44
screenshots and live in `seed_categories.py`. Re-running that command syncs the
permanent presets and prunes categories no longer listed; it never touches
user-added (`is_custom=True`) options.

## Authentication & user registry (`accounts/`)

- Built-in Django `User`, **`username == email`**, email unique (partial index,
  migration `accounts/0002`). No custom user model.
- `accounts/auth_backends.EmailBackend` logs people in by email + password
  (case-insensitive); the standard `ModelBackend` stays enabled for admin.
- URLs under `/accounts/`: `login`, `logout` (POST), `signup`, `password_change`,
  `password_reset*`, plus fixed aliases `password-login/` (name
  `password_login`) and `simple-login/` (name `simple_login`) so both flows are
  always reachable. Templates in `templates/accounts/`.
- `signup` = name + email + password (Django password validators). Creates the
  user and logs them in. Enforces one-email-one-account; only an admin can
  reassign an email (edit it in `/admin/`). **Password-strength errors are
  `add_error`'d onto the password field** and the template renders both
  per-field and non-field errors (a raised `ValidationError` in `clean()` was
  previously invisible - the original "signup does nothing" bug).

### Testing mode (`BEDTRACKER_SIMPLE_LOGIN`)
- `settings.SIMPLE_LOGIN` (env `BEDTRACKER_SIMPLE_LOGIN=true`). Reversible, no
  data migration, nothing deleted.
- ON: `name="login"` routes to `accounts.views.simple_login` (name field only →
  straight to the board). `signup` redirects to it. Topbar shows "Switch name"
  and hides the password link.
- OFF: `name="login"` routes to the real `LoginView`; normal signup/login.
- `simple_login` calls `get_or_create_testing_user(name)`: one `User` per
  slugified name, `username=<slug>.test@simple.local`, `email` same, unusable
  password, `first_name` = the entered name. Same name ⇒ same identity across
  sessions ⇒ consistent `actor_name` in the activity log. Each browser session
  keeps its own name (normal Django session auth). These rows ARE the
  testing-user registry, visible in `/admin/` (filter by the email suffix).
- Real password login stays usable at `/accounts/password-login/` even in
  testing mode (e.g. for a superuser). Admin login (`/admin/login/`) is
  unaffected by the switch.
- Branding via `accounts/context_processors.flags`: `app_name` =
  "WaniaS2 BedTracker", `app_subtitle` = "Surgical Unit 2" (registered as a
  template context processor).
- Password reset emails print to the console in dev; set `BEDTRACKER_EMAIL_*`
  (e.g. a free Gmail app password) to send real ones.
- `accounts.models.LoginEvent` records every login (user, time, IP, UA) via the
  `user_logged_in` signal (`accounts/signals.py`).
- **Developer-only registry** = Django admin (`/admin/`, staff-only, so ordinary
  ward users never see it). `accounts/admin.py` customises the User list
  (email / name / last_login / date_joined / login count, LoginEvent inline)
  and registers LoginEvent read-only. `board/admin.py` ActivityEvent list shows
  `actor` + filter.
- Ordinary ward users are **not** staff; the developer is a superuser
  (`python manage.py createsuperuser`).

## Local backups (`backup/` - independent of the web app)

Standard-library Python script + a Windows Scheduled Task. See
`backup/README.md`. Backs up SQLite now, PostgreSQL later
(`DB_KIND=postgres` in `backup/backup.env`). Everything in `backup/` except the
scripts is git-ignored.
- `backup/backup_bedtracker.py` - `--force` / `--status` / `--verify FILE` /
  `--restore FILE --target …`.
- Sunday only, every 2h for 12h, only when online, resumes after missed runs,
  keeps a new file only if the DB changed (uncompressed SHA-256), retention =
  `RETENTION_DAYS` daily then `RETENTION_WEEKS` weekly. Verifies each backup
  (`PRAGMA integrity_check` / `pg_restore --list`). `manifest.json` + `backup.log`.
- `backup/register_backup_task.ps1` registers the task (no admin, runs only when
  signed in, `StartWhenAvailable` + `RunOnlyIfNetworkAvailable`).
- Config in `backup/backup.env` (copy from `.example`); never contains a
  password (PostgreSQL uses `PGPASSWORD` / `pgpass.conf`).

## Deployment - $0 options (`DEPLOY.md`)

Render/Railway/Fly all now want a card; Railway's **trial** is the exception.
- **A. Railway + Neon** - card-free **trial** (30 days full, then ~$1/mo credit
  ≈ a few days/mo). Good for a pilot. `railway.json` + `build.sh` + `/healthz/`.
- **B. Self-host Windows PC + Tailscale Funnel** - **permanent $0, no card**,
  public HTTPS URL. `waitress-serve`, SQLite kept (`BEDTRACKER_ALLOW_SQLITE=true`).
- **C. Hospital LAN** - `waitress-serve --host=0.0.0.0`, `ALLOWED_HOSTS=*`, HTTP.
- **D. Render + Neon** - `render.yaml` still in repo; needs a card on file.

`requirements.txt`: `gunicorn` (Linux hosts) + `waitress` (Windows self-host).
Settings auto-add `RAILWAY_PUBLIC_DOMAIN` / `RENDER_EXTERNAL_HOSTNAME` to
ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS. `not DEBUG` + SQLite guard has a
`BEDTRACKER_ALLOW_SQLITE=true` escape hatch. `CSRF_TRUSTED_ORIGINS` skips `*`.
Verified: `check --deploy` clean (Railway & Render configs), CSRF login POST
works over plain HTTP (B/C), `waitress` serves on Windows.

Deployment files (all committed): `render.yaml` (Blueprint), `build.sh`
(`pip install` + `collectstatic` + `migrate`), `Procfile`, `runtime.txt`
(python-3.13.1), `.gitattributes` (LF endings so `build.sh` runs on Linux).

Production settings (`config/settings.py`, active when `BEDTRACKER_DEBUG=false`):
- DB resolved as: `DATABASE_URL` (dj-database-url, `ssl_require=True`) →
  `BEDTRACKER_DB=postgres` + `BEDTRACKER_DB_*` → SQLite. **Hard guard**: raises
  `ImproperlyConfigured` if production falls through to SQLite.
- WhiteNoise middleware + `CompressedManifestStaticFilesStorage` serve static
  files from the app process (`STORAGES`; plain storage under tests).
- `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, HSTS (1yr), secure cookies,
  nosniff. `CSRF_TRUSTED_ORIGINS` from `ALLOWED_HOSTS` +
  `BEDTRACKER_CSRF_TRUSTED_ORIGINS`.
- `LOGGING` → stderr (host captures it). `django.request` errors at ERROR.
- `python manage.py check --deploy` passes clean with a real secret key.
- `gunicorn config.wsgi:application` is the start command.
- `/healthz/` (`board.views.healthz`, `@login_not_required`) = health check,
  also pings the DB.

Custom domain later: add it in Render, add it to `BEDTRACKER_ALLOWED_HOSTS` +
`BEDTRACKER_CSRF_TRUSTED_ORIGINS`. No code change.

## PWA (installable web app)

- `templates/manifest.webmanifest` and `templates/sw.js` served from the site
  root (`config/urls.py`, `TemplateView` + `login_not_required`) so the service
  worker scope is `/`. `static/icon.svg` is the app icon.
- `base.html` links the manifest, theme-color, apple-touch meta, and registers
  the SW. The SW is cache-first for `/static/`, **network-first for everything
  else** (clinical pages never served stale). Bump `CACHE` in `sw.js` + the
  `?v=N` on `board.css` together when assets change.

## Mobile / responsive

Desktop layout unchanged. `static/board.css` has a `@media (max-width: 600px)`
block: tighter topbar/summary, **bed & activity panels become full-screen
sheets** (`.panel width:100%`, no border/backdrop), Order/Chase Labs stack
instead of side-by-side, larger tap targets, all inputs 16px (no iOS zoom).
`viewport-fit=cover` in the meta tag.

## Still not built (by prior agreement)

Orders tab, multi-bed grouping in the activity feed, hospital-system lab
integration.
