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

# Cài đặt các dependencies cơ bản trước
COPY requirements-base.txt .
RUN pip install -r requirements-base.txt

# Cài đặt các dependencies Django
COPY requirements-django.txt .
RUN pip install -r requirements-django.txt

# Cài đặt các dependencies khác
COPY requirements-extra.txt .
RUN pip install -r requirements-extra.txt

ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=WebDjango.settings

# Copy toàn bộ project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port 8001
EXPOSE 8001

# Command để chạy server với các tham số phù hợp
CMD ["daphne", \
     "-b", "0.0.0.0", \
     "-p", "8001", \
     "--websocket-timeout", "86400", \
     "--proxy-headers", \
     "--access-log", "-", \
     "--websocket-ping-interval", "20", \
     "--websocket-ping-timeout", "10", \
     "WebDjango.asgi:application"] 