FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r backend/requirements.txt

CMD ["python", "backend/app.py"]