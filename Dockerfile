# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Copy project definition and source code
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY tests/ /app/tests/

# Install the package defined in pyproject.toml including dev dependencies
RUN pip install --no-cache-dir .[dev]

# Expose port 8080 for Cloud Run or other services
EXPOSE 8080

# Command to run the application using the module entry point
# This relies on the package being installed correctly
CMD ["python", "-m", "ledger_cfo"] 