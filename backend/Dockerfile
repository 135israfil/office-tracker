# 3.10 is the newest Python Django 4.0 supports — see requirements.txt for why 4.0 is
# pinned (the production target's PostgreSQL 10.23 requires it).
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies are copied and installed before the source so that editing code
# does not invalidate the (slow) pip layer.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements-dev.txt

COPY . .

# Run as a non-root, unprivileged user. The image ships no other services that need
# root, and the app binds to 8000 (unprivileged), so no capabilities are required.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
