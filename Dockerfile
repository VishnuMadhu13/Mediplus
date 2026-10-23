FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=mediplus.settings_container

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static files at build time (the container filesystem is read-only in K8s).
RUN DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput --skip-checks \
    && chmod +x /app/docker-entrypoint.sh \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/media \
    && chown -R appuser:appuser /app/data /app/media

USER 1000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/index', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
