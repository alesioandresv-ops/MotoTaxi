# Multi-stage build: Build frontend (if needed) and run Flask backend
FROM python:3.12-slim

WORKDIR /app

# Copy all files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Expose port
EXPOSE 5000

# Run Flask app
CMD ["python", "backend/app.py"]

