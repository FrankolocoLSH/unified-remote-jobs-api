FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jobsapi/ ./jobsapi/

# SQLite data lives here; mount a persistent volume on Render/Railway.
VOLUME /app/data
ENV JOBS_DB=/app/data/jobs.db

EXPOSE 8000
CMD ["sh", "-c", "uvicorn jobsapi.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
