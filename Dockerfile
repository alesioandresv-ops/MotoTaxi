FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN chmod +x start.sh && pip install --no-cache-dir -r backend/requirements.txt

CMD ["/app/start.sh"]