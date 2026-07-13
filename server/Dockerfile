FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY relay_server.py .

# Fly.io will set the PORT environment variable, but we set a default
ENV HOST="0.0.0.0"
ENV PORT=8080
EXPOSE 8080

CMD ["python", "relay_server.py"]
