# Sử dụng Python 3.8-slim làm base image
FROM python:3.8-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt các dependencies hệ thống
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt pip mới nhất
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install -r requirements.txt

ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=WebDjango.settings

# Copy toàn bộ project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port 8001
EXPOSE 8001

# Command để chạy server với Uvicorn
CMD ["uvicorn", \
     "WebDjango.asgi:application", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--workers", "4", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--timeout-keep-alive", "86400", \
     "--ws", "auto", \
     "--ws-ping-interval", "20", \
     "--ws-ping-timeout", "10", \
     "--log-level", "info"] 