FROM python:3.9-slim

WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn flask

# Copy the application code
COPY . .

# Set environment variables
ENV PORT=8080
ENV FLASK_PORT=8080
ENV STREAMLIT_PORT=8501

# Run the combined Flask + Streamlit application
CMD python app.py 