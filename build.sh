#!/usr/bin/env bash
# Runs on the host every time you deploy.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
