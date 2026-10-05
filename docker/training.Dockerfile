FROM python:3.13-slim

WORKDIR /app
COPY requirements/training.txt ./requirements/training.txt
RUN pip install --no-cache-dir -r requirements/training.txt
COPY src/ ./src/

CMD ["python", "-m", "src.train", "--data", "/app/data/btcusd_daily.csv", "--output", "/app/models"]
