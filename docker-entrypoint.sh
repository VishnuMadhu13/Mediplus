#!/bin/sh
set -e

# Apply migrations (--run-syncdb creates tables for the mediplus app, which has no migrations; fails fast if the project does not load), then start gunicorn.
python manage.py migrate --noinput --run-syncdb

exec gunicorn mediplus.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --worker-tmp-dir /dev/shm \
  --access-logfile - \
  --error-logfile -
