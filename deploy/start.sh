#!/bin/sh
# Start command for single-container hosts such as Render/Railway.
# (docker-compose uses its own `migrate` service instead.)
set -e
python manage.py migrate --noinput
# Demo users are created only if DEMO_PASSWORD is set. Leave it unset to skip seeding.
if [ -n "$DEMO_PASSWORD" ]; then
  python manage.py seed_demo --password "$DEMO_PASSWORD"
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_WORKERS:-2} --access-logfile -