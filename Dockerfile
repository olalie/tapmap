FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install .

ENV TAPMAP_PORT=8050
ENV TAPMAP_HOST=0.0.0.0
ENV TAPMAP_DATA_DIR=/data

EXPOSE 8050

ENTRYPOINT ["python", "-m", "tapmap"]
CMD []
