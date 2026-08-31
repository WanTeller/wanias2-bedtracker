#!/usr/bin/env python3
"""
BedTracker database backup - independent of the web app.

Standard library only. Works with the development SQLite database now and with
a hosted PostgreSQL database later (set DB_KIND=postgres in backup.env).

Typical use (Windows Task Scheduler runs this every 2h on Sundays):

    python backup_bedtracker.py                # make a backup if one is due
    python backup_bedtracker.py --force        # ignore the "Sunday only" / interval rules
    python backup_bedtracker.py --status       # show recent backups
    python backup_bedtracker.py --verify LATEST
    python backup_bedtracker.py --restore <file> --target <path-or-dbname>

Config is read from backup.env (same folder) or from environment variables.
Passwords are NEVER read from source - for PostgreSQL use PGPASSWORD or, better,
%APPDATA%\\postgresql\\pgpass.conf.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg: dict[str, str] = {}
    env_file = os.path.join(HERE, "backup.env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    # Environment variables win over the file.
    for k, v in os.environ.items():
        if k.startswith(("DB_", "PG_", "BACKUP_", "RUN_", "REQUIRE_",
                         "RETENTION_", "MIN_", "SQLITE_")):
            cfg[k] = v

    def g(key, default):
        return cfg.get(key, default)

    return {
        "DB_KIND": g("DB_KIND", "sqlite").lower(),
        "SQLITE_PATH": g("SQLITE_PATH", os.path.join(PROJECT_ROOT, "db.sqlite3")),
        "PG_HOST": g("PG_HOST", "localhost"),
        "PG_PORT": g("PG_PORT", "5432"),
        "PG_DB": g("PG_DB", "bedtracker"),
        "PG_USER": g("PG_USER", "bedtracker"),
        "PG_DUMP": g("PG_DUMP", "pg_dump"),
        "PG_RESTORE": g("PG_RESTORE", "pg_restore"),
        "BACKUP_DIR": g("BACKUP_DIR", HERE),
        "RUN_WEEKDAY": g("RUN_WEEKDAY", "6"),          # Mon=0..Sun=6; "" = any day
        "REQUIRE_INTERNET": g("REQUIRE_INTERNET", "true").lower() in ("1", "true", "yes"),
        "RETENTION_DAYS": int(g("RETENTION_DAYS", "14")),
        "RETENTION_WEEKS": int(g("RETENTION_WEEKS", "8")),
        "MIN_INTERVAL_MINUTES": int(g("MIN_INTERVAL_MINUTES", "90")),
    }


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def log(cfg, msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    path = os.path.join(cfg["BACKUP_DIR"], "backup.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
            shutil.move(path, path + ".1")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_online() -> bool:
    for host in ("1.1.1.1", "8.8.8.8", "9.9.9.9"):
        try:
            with socket.create_connection((host, 443), timeout=4):
                return True
        except OSError:
            continue
    return False


def manifest_path(cfg) -> str:
    return os.path.join(cfg["BACKUP_DIR"], "manifest.json")


def load_manifest(cfg) -> dict:
    try:
        with open(manifest_path(cfg), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"backups": []}


def save_manifest(cfg, data: dict) -> None:
    with open(manifest_path(cfg), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# --------------------------------------------------------------------------- #
# dump
# --------------------------------------------------------------------------- #
def dump_sqlite(cfg, dest_uncompressed: str) -> None:
    src = cfg["SQLITE_PATH"]
    if not os.path.exists(src):
        raise FileNotFoundError(f"SQLite database not found: {src}")
    # Online backup API - safe to run while the app is using the database.
    with sqlite3.connect(src) as source, sqlite3.connect(dest_uncompressed) as dst:
        source.backup(dst)


def dump_postgres(cfg, dest: str) -> None:
    cmd = [
        cfg["PG_DUMP"], "-Fc", "--no-owner", "--no-privileges",
        "-h", cfg["PG_HOST"], "-p", cfg["PG_PORT"],
        "-U", cfg["PG_USER"], "-d", cfg["PG_DB"], "-f", dest,
    ]
    subprocess.run(cmd, check=True)


def make_backup(cfg, force: bool = False) -> int:
    os.makedirs(cfg["BACKUP_DIR"], exist_ok=True)
    manifest = load_manifest(cfg)
    last = manifest["backups"][-1] if manifest["backups"] else None

    # Rule 1: only on the configured weekday (Sunday by default).
    wd = cfg["RUN_WEEKDAY"]
    if wd != "" and not force and datetime.now().weekday() != int(wd):
        log(cfg, "skip: not the scheduled backup day")
        return 0

    # Rule 2: needs an internet connection (matters once the DB is hosted).
    if cfg["REQUIRE_INTERNET"] and not force and not is_online():
        log(cfg, "skip: no internet connection")
        return 0

    # Rule 3: don't churn - if the last backup is very recent, only proceed
    # when the data has actually changed (checked by hash below anyway, but this
    # avoids doing a full dump every 2 hours for nothing).
    if last and not force:
        age_min = (time.time() - last["epoch"]) / 60
        if age_min < cfg["MIN_INTERVAL_MINUTES"]:
            log(cfg, f"skip: last backup {age_min:.0f} min ago "
                     f"(< {cfg['MIN_INTERVAL_MINUTES']})")
            return 0

    kind = cfg["DB_KIND"]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmpdir = tempfile.mkdtemp(prefix="bedtracker-bak-")
    try:
        if kind == "sqlite":
            raw = os.path.join(tmpdir, "db.sqlite3")
            dump_sqlite(cfg, raw)
            # Hash the *uncompressed* database - this is a true "did the data
            # change" check (gzip headers vary between runs, dump headers don't).
            content_hash = sha256_file(raw)
            final_name = f"bedtracker-{ts}.sqlite3.gz"
            final = os.path.join(cfg["BACKUP_DIR"], final_name)
            # mtime=0 keeps the gzip deterministic too.
            with open(raw, "rb") as fin, gzip.GzipFile(
                final, "wb", compresslevel=6, mtime=0
            ) as fout:
                shutil.copyfileobj(fin, fout)
        elif kind == "postgres":
            final_name = f"bedtracker-{ts}.dump"
            final = os.path.join(cfg["BACKUP_DIR"], final_name)
            dump_postgres(cfg, final)
            content_hash = sha256_file(final)  # best-effort for pg custom format
        else:
            log(cfg, f"error: unknown DB_KIND '{kind}'")
            return 2

        # Rule 4: identical to the previous backup? Throw it away.
        if last and last.get("content_sha256") == content_hash:
            os.remove(final)
            log(cfg, "skip: database unchanged since last backup")
            return 0

        ok, detail = verify_file(cfg, final)
        size = os.path.getsize(final)
        manifest["backups"].append({
            "name": final_name,
            "created": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "kind": kind,
            "content_sha256": content_hash,
            "sha256": sha256_file(final),
            "size": size,
            "verified": ok,
            "verify_detail": detail,
        })
        save_manifest(cfg, manifest)
        prune(cfg, manifest)
        log(cfg, f"backup OK: {final_name}  ({size/1024:.0f} KB)  "
                 f"verify={'ok' if ok else 'FAILED: ' + detail}")
        return 0 if ok else 3
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def verify_file(cfg, path: str) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, "file missing"
    try:
        if path.endswith(".sqlite3.gz"):
            with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tf:
                tmp = tf.name
            try:
                with gzip.open(path, "rb") as fin, open(tmp, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                con = sqlite3.connect(tmp)
                result = con.execute("PRAGMA integrity_check").fetchone()[0]
                tables = con.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()[0]
                con.close()
                if result != "ok":
                    return False, f"integrity_check: {result}"
                if tables < 5:
                    return False, f"only {tables} tables - looks empty"
                return True, f"integrity ok, {tables} tables"
            finally:
                os.remove(tmp)
        elif path.endswith(".dump"):
            out = subprocess.run(
                [cfg["PG_RESTORE"], "--list", path],
                capture_output=True, text=True,
            )
            if out.returncode != 0:
                return False, out.stderr.strip()[:150]
            n = len([ln for ln in out.stdout.splitlines() if ln and not ln.startswith(";")])
            return (n > 0), f"{n} archive entries"
        return False, "unknown backup type"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# retention
# --------------------------------------------------------------------------- #
def prune(cfg, manifest: dict) -> None:
    now = time.time()
    keep_days = cfg["RETENTION_DAYS"] * 86400
    keep_weeks = cfg["RETENTION_WEEKS"]

    weekly_seen: set[str] = set()
    survivors = []
    # newest first
    for b in sorted(manifest["backups"], key=lambda x: x["epoch"], reverse=True):
        age = now - b["epoch"]
        if age <= keep_days:
            survivors.append(b)
            continue
        wk = datetime.fromtimestamp(b["epoch"]).strftime("%G-W%V")
        if wk not in weekly_seen and len(weekly_seen) < keep_weeks:
            weekly_seen.add(wk)
            survivors.append(b)

    keep_names = {b["name"] for b in survivors}
    for b in manifest["backups"]:
        if b["name"] not in keep_names:
            p = os.path.join(cfg["BACKUP_DIR"], b["name"])
            if os.path.exists(p):
                os.remove(p)
                log(cfg, f"retention: removed {b['name']}")
    manifest["backups"] = sorted(survivors, key=lambda x: x["epoch"])
    save_manifest(cfg, manifest)


# --------------------------------------------------------------------------- #
# restore
# --------------------------------------------------------------------------- #
def restore(cfg, source_file: str, target: str) -> int:
    src = source_file
    if src.upper() == "LATEST":
        m = load_manifest(cfg)
        if not m["backups"]:
            log(cfg, "restore: no backups in manifest")
            return 1
        src = m["backups"][-1]["name"]
    if not os.path.isabs(src):
        src = os.path.join(cfg["BACKUP_DIR"], src)
    if not os.path.exists(src):
        log(cfg, f"restore: source not found: {src}")
        return 1

    if src.endswith(".sqlite3.gz"):
        if os.path.exists(target):
            log(cfg, f"restore: refusing to overwrite existing file {target}")
            return 1
        with gzip.open(src, "rb") as fin, open(target, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        con = sqlite3.connect(target)
        chk = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        log(cfg, f"restored SQLite -> {target}  (integrity_check: {chk})")
        return 0 if chk == "ok" else 3

    if src.endswith(".dump"):
        # target = name of a SEPARATE database you have already created with
        #   createdb <target>
        cmd = [cfg["PG_RESTORE"], "--clean", "--if-exists", "--no-owner",
               "-h", cfg["PG_HOST"], "-p", cfg["PG_PORT"], "-U", cfg["PG_USER"],
               "-d", target, src]
        rc = subprocess.run(cmd).returncode
        log(cfg, f"pg_restore -> database '{target}' exit {rc}")
        return rc

    log(cfg, "restore: unrecognised backup file type")
    return 1


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
def status(cfg) -> int:
    m = load_manifest(cfg)
    if not m["backups"]:
        print("No backups yet.")
        return 0
    print(f"{'FILE':38} {'WHEN':20} {'SIZE':>9}  VERIFIED")
    for b in m["backups"][-15:]:
        when = datetime.fromisoformat(b["created"]).astimezone().strftime("%Y-%m-%d %H:%M")
        print(f"{b['name']:38} {when:20} {b['size']/1024:8.0f}K  "
              f"{'yes' if b.get('verified') else 'NO'}")
    print(f"\n{len(m['backups'])} kept in {cfg['BACKUP_DIR']}")
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="BedTracker database backup")
    ap.add_argument("--force", action="store_true",
                    help="ignore the weekday / interval / internet checks")
    ap.add_argument("--status", action="store_true", help="list recent backups")
    ap.add_argument("--verify", metavar="FILE",
                    help="verify a backup file (name in backup dir, path, or LATEST)")
    ap.add_argument("--restore", metavar="FILE",
                    help="restore a backup (name, path, or LATEST)")
    ap.add_argument("--target", metavar="PATH_OR_DBNAME",
                    help="where to restore to (a NEW .sqlite3 path, or a "
                         "separate PostgreSQL database name)")
    args = ap.parse_args()
    cfg = load_config()

    if args.status:
        return status(cfg)

    if args.verify:
        f = args.verify
        if f.upper() == "LATEST":
            m = load_manifest(cfg)
            f = m["backups"][-1]["name"] if m["backups"] else ""
        if f and not os.path.isabs(f):
            f = os.path.join(cfg["BACKUP_DIR"], f)
        ok, detail = verify_file(cfg, f)
        print(f"{'OK' if ok else 'FAILED'}: {detail}")
        return 0 if ok else 1

    if args.restore:
        if not args.target:
            print("--restore needs --target")
            return 2
        return restore(cfg, args.restore, args.target)

    return make_backup(cfg, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
