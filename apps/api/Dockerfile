FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 unzip \
    && rm -rf /var/lib/apt/lists/*

COPY packages/ff_core /app/packages/ff_core
RUN pip install --no-cache-dir /app/packages/ff_core

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/api /app/apps/api
ENV PYTHONPATH=/app/apps/api

WORKDIR /app/apps/api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
