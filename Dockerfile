# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

# Set work directory
WORKDIR /app

# Install system dependencies required for psycopg2-binary if needed
# Uncomment the following line if you encounter build issues with psycopg2
# RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code into the container
COPY ./src /app/src

# Expose the port the app runs on (Cloud Run expects 8080 by default)
EXPOSE 8080

# Define the command to run the application using Gunicorn with Uvicorn workers for async support
# Assumes src/ledger_cfo/__main__.py defines the Flask app instance named 'app'
# The worker count can be adjusted based on expected load and Cloud Run instance size
# Use the PORT environment variable provided by Cloud Run
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "src.ledger_cfo.__main__:app"] 