#!/bin/bash

# === CONFIGURATION ===
PROJECT_DIR="/WebDjango"              # Thư mục chứa dự án Django
VENV_DIR="/WebDjango/.venv"          # Thư mục chứa virtualenv
DJANGO_MODULE="WebDjango.asgi:application"  # Module ASGI của dự án
BRANCH="main"                        # Nhánh Git
LOG_FILE="daphne.log"
MAX_LOG_SIZE=10M                     # Kích thước tối đa của file log
BACKUP_DIR="docker_backups"          # Thư mục lưu backup
PROJECT_NAME="webdjango"             # Tên project trong docker-compose

# === ERROR HANDLING ===
set -e  # Exit on error
trap 'echo "Error occurred at line $LINENO. Command: $BASH_COMMAND"' ERR

# === DEPLOY PROCESS ===
echo "Bắt đầu quá trình deploy..."

# 1. Kiểm tra Docker và Docker Compose
echo "Kiểm tra Docker và Docker Compose..."
if ! command -v docker &> /dev/null; then
    echo "Lỗi: Docker chưa được cài đặt"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Lỗi: Docker Compose chưa được cài đặt"
    exit 1
fi

# 2. Kiểm tra thư mục dự án
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Lỗi: Thư mục dự án không tồn tại: $PROJECT_DIR"
    exit 1
fi

# 3. Chuyển đến thư mục dự án
cd $PROJECT_DIR || exit

# 4. Kiểm tra file docker-compose.yml và requirements.txt
if [ ! -f "docker-compose.yml" ]; then
    echo "Lỗi: Không tìm thấy file docker-compose.yml"
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    echo "Lỗi: Không tìm thấy file requirements.txt"
    exit 1
fi

# 5. Xử lý log file
if [ -f "$LOG_FILE" ]; then
    if [ $(stat -f%z "$LOG_FILE") -gt $MAX_LOG_SIZE ]; then
        mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d_%H%M%S)"
    fi
fi

# 6. Backup và xóa containers/volumes cũ
echo "Xử lý containers và volumes cũ..."

# Tạo thư mục backup nếu chưa tồn tại
mkdir -p "$BACKUP_DIR"

# Lấy danh sách volumes của project
VOLUMES=$(docker compose config --format json | jq -r '.volumes | keys[]' 2>/dev/null)

if [ -n "$VOLUMES" ]; then
    echo "Tìm thấy các volumes sau:"
    echo "$VOLUMES"
    
    # Backup volumes trước khi xóa
    for volume in $VOLUMES; do
        echo "Backup volume: $volume"
        docker run --rm -v "$volume":/source -v "$PWD/$BACKUP_DIR":/backup alpine tar czf "/backup/${volume}_$(date +%Y%m%d_%H%M%S).tar.gz" -C /source .
    done
fi

# 7. Dừng và xóa containers
echo "Dừng containers..."
docker compose down

# 8. Xóa volumes cụ thể của project
if [ -n "$VOLUMES" ]; then
    for volume in $VOLUMES; do
        echo "Xóa volume: $volume"
        docker volume rm "$volume" 2>/dev/null || true
    done
fi

# 9. Build lại Docker image
echo "Build lại Docker image..."
docker compose build --no-cache

# 10. Khởi động lại toàn bộ hệ thống
echo "Khởi động lại hệ thống..."
docker compose up -d

# 11. Chờ container sẵn sàng
echo "Chờ container sẵn sàng..."
sleep 10

# 12. Kiểm tra container đã chạy
if ! docker compose ps | grep -q "Up"; then
    echo "Lỗi: Container không khởi động được"
    docker compose logs
    exit 1
fi

# 13. Chạy migrate & collectstatic trong container
echo "Chạy migrate và thu thập static files..."
docker compose exec $PROJECT_NAME bash -c "
    python manage.py check &&
    python manage.py migrate &&
    python manage.py collectstatic --noinput --clear
"

# 14. Kiểm tra kết nối MongoDB
echo "Kiểm tra kết nối MongoDB..."
docker compose exec $PROJECT_NAME python -c "
import pymongo
from django.conf import settings
import sys

def check_mongodb_connection():
    try:
        client = pymongo.MongoClient(
            settings.MONGODB_URI,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT,
            connectTimeoutMS=settings.MONGODB_CONNECTION_TIMEOUT,
            socketTimeoutMS=settings.MONGODB_SOCKET_TIMEOUT,
            retryWrites=settings.MONGODB_RETRY_WRITES,
            w=settings.MONGODB_W
        )
        # Test connection
        client.server_info()
        # Test database access
        db = client[settings.MONGODB_DATABASE]
        db.command('ping')
        print('Kết nối MongoDB thành công!')
        return True
    except Exception as e:
        print(f'Lỗi kết nối MongoDB: {str(e)}')
        return False

if not check_mongodb_connection():
    sys.exit(1)
"

# Kiểm tra kết quả
if [ $? -ne 0 ]; then
    echo "Lỗi: Không thể kết nối đến MongoDB"
    exit 1
fi

# 15. Dừng Daphne nếu đang chạy
echo "Dừng Daphne nếu đang chạy..."
PID=$(ps aux | grep daphne | grep "$DJANGO_MODULE" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    kill "$PID"
    echo "Đã dừng Daphne (PID $PID)"
else
    echo "Không tìm thấy Daphne đang chạy."
fi

# 16. Khởi động lại Daphne
echo "Khởi động lại Daphne..."
nohup daphne -b 0.0.0.0 -p 8001 $DJANGO_MODULE > "$LOG_FILE" 2>&1 &

# 17. Kiểm tra Daphne đã chạy
sleep 5
if ! ps aux | grep daphne | grep -q "$DJANGO_MODULE"; then
    echo "Lỗi: Daphne không khởi động được"
    cat "$LOG_FILE"
    exit 1
fi

# 18. Xác nhận quá trình hoàn tất
echo "Deploy thành công!"
echo "Kiểm tra logs tại: $LOG_FILE"
