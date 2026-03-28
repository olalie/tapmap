FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TAPMAP_PORT=8050
ENV TAPMAP_HOST=0.0.0.0
ENV TAPMAP_DATA_DIR=/data
# Optional: set MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY to enable
# automatic GeoLite2 database downloads.  MAXMIND_UPDATE_INTERVAL_DAYS
# controls the refresh cadence (default: 7 days).
# ENV MAXMIND_ACCOUNT_ID=
# ENV MAXMIND_LICENSE_KEY=
# ENV MAXMIND_UPDATE_INTERVAL_DAYS=7

EXPOSE 8050

CMD ["python", "tapmap.py"]
