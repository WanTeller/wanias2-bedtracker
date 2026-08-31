#!/usr/bin/env bash
# Runs on the host on every deploy (Railway / Render).
set -o errexit

python -m pip install --no-cache-dir -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

# ---- one-time bootstrap, driven by environment variables --------------------
# Leave these in place: each step quietly does nothing once it's already done.

# Create the developer/admin account if DJANGO_SUPERUSER_* vars are set.
# (createsuperuser --noinput reads DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD)
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput \
    || echo "bootstrap: superuser already exists, skipping"
fi

# Load task categories + demo patients if BEDTRACKER_SEED_DEMO=true.
if [ "${BEDTRACKER_SEED_DEMO:-}" = "true" ]; then
  python manage.py seed_demo || echo "bootstrap: seed_demo skipped"
fi
