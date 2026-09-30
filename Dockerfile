FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collect static files at build time (no database needed)
RUN DB_ENGINE=sqlite SECRET_KEY=build python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir -p /app/media && chown -R app:app /app/media
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
