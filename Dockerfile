FROM python:3.13-slim

# Debian security updates published after the base image
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# pip is needed only at build time
RUN PIP_NO_CACHE_DIR=1 pip install . \
    && pip uninstall -y pip

ENV TAPMAP_PORT=8050
ENV TAPMAP_HOST=0.0.0.0
ENV TAPMAP_DATA_DIR=/data

EXPOSE 8050

ENTRYPOINT ["python", "-m", "tapmap"]
CMD []
