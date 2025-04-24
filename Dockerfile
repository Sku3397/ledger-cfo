FROM python:3.9-slim

WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set environment variables
ENV PORT=8080

# Run the app
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app 