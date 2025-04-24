# Sử dụng Python 3.10 làm base image
FROM python:3.10-slim

# Thiết lập biến môi trường
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt các dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY . .

# Expose port 8000
EXPOSE 8001

# Chạy gunicorn
CMD ["daphne", "-b", "0.0.0.0", "-p", "8001", "--websocket-timeout", "86400", "--proxy-headers", "--access-log", "-", "WebDjango.asgi:application"] 