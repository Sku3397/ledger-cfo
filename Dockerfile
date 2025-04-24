FROM python:3.9-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PORT=8080

# Run the application with gunicorn
# This will use the Flask app instance imported in main.py
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app 