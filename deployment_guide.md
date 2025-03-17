# Hướng dẫn triển khai ứng dụng lên Ubuntu Server

## 1. Chuẩn bị Server Ubuntu

```bash
# Cập nhật hệ thống
sudo apt update
sudo apt upgrade -y

# Cài đặt các gói cần thiết
sudo apt install python3-pip python3-venv nginx git -y
```

## 2. Tạo thư mục và môi trường ảo

```bash
# Tạo thư mục cho ứng dụng
mkdir -p /var/www/emailmanager
cd /var/www/emailmanager

# Tạo và kích hoạt môi trường ảo
python3 -m venv venv
source venv/bin/activate
```

## 3. Clone và cài đặt ứng dụng

```bash
# Clone mã nguồn từ repository (thay thế URL)
git clone <your-repository-url> .

# Cài đặt các thư viện
pip install -r requirements.txt
```

## 4. Cấu hình môi trường

Tạo file `.env` trong thư mục gốc:

```bash
# Tạo và chỉnh sửa file .env
nano .env
```

Thêm các biến môi trường sau:

```
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
MONGO_URI=mongodb://username:password@host:port/database
```

## 5. Cấu hình Gunicorn

Tạo file systemd service:

```bash
sudo nano /etc/systemd/system/emailmanager.service
```

Thêm nội dung sau:

```ini
[Unit]
Description=Email Manager Gunicorn Daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/emailmanager
ExecStart=/var/www/emailmanager/venv/bin/gunicorn --workers 3 --bind unix:/var/www/emailmanager/emailmanager.sock WebDjango.wsgi:application

[Install]
WantedBy=multi-user.target
```

## 6. Cấu hình Nginx

Tạo file cấu hình Nginx:

```bash
sudo nano /etc/nginx/sites-available/emailmanager
```

Thêm nội dung sau:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        root /var/www/emailmanager;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/emailmanager/emailmanager.sock;
    }
}
```

## 7. Kích hoạt cấu hình

```bash
# Thu thập static files
python manage.py collectstatic

# Cấp quyền cho thư mục
sudo chown -R www-data:www-data /var/www/emailmanager

# Kích hoạt Nginx config
sudo ln -s /etc/nginx/sites-available/emailmanager /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx

# Kích hoạt Gunicorn service
sudo systemctl start emailmanager
sudo systemctl enable emailmanager
```

## 8. Kiểm tra hoạt động

```bash
# Kiểm tra trạng thái service
sudo systemctl status emailmanager

# Kiểm tra logs
sudo journalctl -u emailmanager
```

## Xử lý sự cố

1. Nếu gặp lỗi permission:
```bash
sudo chown -R www-data:www-data /var/www/emailmanager
sudo chmod -R 755 /var/www/emailmanager
```

2. Nếu cần restart services:
```bash
sudo systemctl restart emailmanager
sudo systemctl restart nginx
```

3. Kiểm tra logs:
```bash
sudo tail -f /var/log/nginx/error.log
sudo journalctl -u emailmanager
``` 