FROM python:3.11-slim

# Install system dependencies including FFmpeg and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-freefont-ttf \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Inside the container we must listen on all interfaces; set STUDIO_API_TOKEN in .env
CMD ["python", "main.py", "--server", "--host", "0.0.0.0", "--port", "8000"]
