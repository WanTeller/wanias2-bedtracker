# BedTracker local backups

An independent backup system for the BedTracker database. It has **no
dependency on the web app** - it is a single standard-library Python script
plus a Windows Scheduled Task.

- Backups are written to this folder (`…\BedTracker\backup\`).
- They are **git-ignored** - nothing here except the scripts is committed.
- Cost: **$0**. Uses built-in Python + built-in Windows Task Scheduler.
- Works with the development **SQLite** database now, and a hosted
  **PostgreSQL** database later (`DB_KIND=postgres` in `backup.env`).

## Files

| File | Purpose |
|---|---|
| `backup_bedtracker.py` | The backup / verify / restore script |
| `backup.env.example` | Config template - copy to `backup.env` and edit |
| `register_backup_task.ps1` | One-time Scheduled Task setup |
| `manifest.json` | Auto-written record of every kept backup (hash, size, verified) |
| `backup.log` | Auto-written run log |

## How it behaves (Anki-style)

- Runs **every Sunday**, repeating **every 2 hours for 12 hours**.
- Runs **only when a network connection is available**.
- If the PC was off at a scheduled time, Task Scheduler runs it **as soon as
  the PC is next on** (`StartWhenAvailable`).
- A new backup file is only kept **if the database actually changed** since the
  last one (SHA-256 comparison) - no duplicate clutter.
- Retention is configurable: keep every backup for `RETENTION_DAYS` (default
  14), then one per week for `RETENTION_WEEKS` (default 8). Older ones are
  deleted automatically.
- Every backup is **verified** right after it is made (see below).

## One-time setup on your Windows PC

1. Copy the config template and (optionally) edit it:

   ```powershell
   cd C:\Users\Hassan\Desktop\WanTeller\Projects\BedTracker\backup
   copy backup.env.example backup.env
   ```

   For development the defaults are fine - it will back up
   `..\db.sqlite3`. During development you may want to set
   `REQUIRE_INTERNET=false` (a local file backup doesn't need the internet).

2. Register the scheduled task (ordinary PowerShell, no admin needed):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\register_backup_task.ps1
   ```

3. Test it immediately:

   ```powershell
   Start-ScheduledTask -TaskName "BedTracker Weekly Backup"
   python .\backup_bedtracker.py --status
   ```

   (Or just run `python .\backup_bedtracker.py --force` to make one now,
   ignoring the "Sunday only" rule.)

That's it. Nothing else is needed day to day.

## Verifying a backup

Verification runs automatically after each backup and the result is stored in
`manifest.json`. To check a file yourself:

```powershell
python .\backup_bedtracker.py --verify LATEST
python .\backup_bedtracker.py --verify bedtracker-20260907-1003xx.sqlite3.gz
```

- **SQLite**: the file is decompressed, opened, and `PRAGMA integrity_check`
  must return `ok`, with a sane number of tables.
- **PostgreSQL**: `pg_restore --list` must succeed and list archive entries.

## Restoring

### Test restore (safe - into a SEPARATE database)

**SQLite:**

```powershell
# 1. Restore into a NEW file (the script refuses to overwrite an existing one)
python .\backup_bedtracker.py --restore LATEST --target C:\temp\bedtracker-test.sqlite3

# 2. Point a throwaway Django at it and check it
cd C:\Users\Hassan\Desktop\WanTeller\Projects\BedTracker
$env:BEDTRACKER_SQLITE_PATH = "C:\temp\bedtracker-test.sqlite3"
.\.venv\Scripts\python.exe manage.py migrate --check
.\.venv\Scripts\python.exe manage.py runserver 8100   # look around, then Ctrl+C
Remove-Item Env:\BEDTRACKER_SQLITE_PATH
```

**PostgreSQL:**

```powershell
createdb bedtracker_restoretest
python .\backup_bedtracker.py --restore LATEST --target bedtracker_restoretest
# inspect with psql, then:  dropdb bedtracker_restoretest
```

### Real restore (into the live database)

**SQLite** - stop the app, then:

```powershell
copy C:\Users\Hassan\Desktop\WanTeller\Projects\BedTracker\db.sqlite3 db.sqlite3.broken
python .\backup\backup_bedtracker.py --restore <file> --target C:\temp\restored.sqlite3
copy C:\temp\restored.sqlite3 C:\Users\Hassan\Desktop\WanTeller\Projects\BedTracker\db.sqlite3
```

**PostgreSQL** - stop the app, then restore into the live DB (this drops and
recreates objects):

```powershell
python .\backup\backup_bedtracker.py --restore <file> --target bedtracker
```

Always test-restore first to confirm the backup is good.

## Security

- No passwords in any file here. For PostgreSQL, use `PGPASSWORD` or
  `%APPDATA%\postgresql\pgpass.conf`.
- The backup folder contains real data once you go live - it stays out of git
  and off any shared drive.
