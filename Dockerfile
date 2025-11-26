# Use an official lightweight Python image
FROM python:3.12-slim

# Install system dependencies needed for pikepdf
RUN apt-get update && apt-get install -y \
    qpdf \
    libqpdf-dev \
    build-essential \
    g++ \
    gcc \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libfreetype6-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r backend/requirements.txt

# Expose port
EXPOSE 5000

# Start FastAPI app
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "5000"]
