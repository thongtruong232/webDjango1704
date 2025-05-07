# Sử dụng Python 3.10 làm base image
FROM python:3.10

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt các dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=WebDjango.settings

# Copy toàn bộ code vào container
COPY . .

# Expose port 8000
EXPOSE 8000

# Chạy gunicorn
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "WebDjango.asgi:application"] 