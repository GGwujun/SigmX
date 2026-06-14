# Overseas info proxy — lightweight FastAPI. Deploy on the overseas server.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 12000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "12000"]
