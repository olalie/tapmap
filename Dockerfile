FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TAPMAP_PORT=8050

EXPOSE 8050

CMD ["python", "tapmap.py"]
