#!/bin/bash

# === CONFIGURATION ===
PROJECT_DIR="/WebDjango"              # Thư mục chứa dự án Django (theo cấu trúc của bạn)
VENV_DIR="/WebDjango/.venv"            # Thư mục chứa virtualenv (nếu có)
DJANGO_MODULE="WebDjango.asgi:application"  # Module ASGI của dự án
BRANCH="main"                         # Nhánh Git bạn sử dụng (có thể là 'main', 'master' hoặc nhánh khác)
LOG_FILE="daphne.log"
MAX_LOG_SIZE=10M  # Kích thước tối đa của file log
BACKUP_DIR="docker_backups"           # Thư mục lưu backup

# === DEPLOY PROCESS ===
echo "Bắt đầu quá trình deploy..."

# 1. Chuyển đến thư mục dự án
cd $PROJECT_DIR || exit

# 2. Kích hoạt virtualenv
echo "Kích hoạt virtualenv..."
source $VENV_DIR/bin/activate

# 3. Xử lý log file
if [ -f "$LOG_FILE" ]; then
    if [ $(stat -f%z "$LOG_FILE") -gt $MAX_LOG_SIZE ]; then
        mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d_%H%M%S)"
    fi
fi

# 4. Build lại Docker image
echo "Build lại Docker image..."
docker compose build

# 5. Backup và xóa containers/volumes cũ
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

# Dừng và xóa containers
echo "Dừng containers..."
docker compose down

# Xóa volumes cụ thể của project
if [ -n "$VOLUMES" ]; then
    for volume in $VOLUMES; do
        echo "Xóa volume: $volume"
        docker volume rm "$volume" 2>/dev/null || true
    done
fi

# 6. Khởi động lại toàn bộ hệ thống
echo "Khởi động lại hệ thống..."
docker compose up -d

# 7. Chờ vài giây để Django container sẵn sàng
echo "Chờ container sẵn sàng..."
sleep 5

# 8. Cài đặt các gói mới (nếu có thay đổi trong requirements.txt)
echo "Cài đặt dependencies mới..."
pip install --no-cache-dir -r requirements.txt

# 9. Chạy migrate & collectstatic bên trong container
echo "Chạy migrate và thu thập static files..."
docker compose exec $PROJECT_NAME bash -c "
  python manage.py migrate &&
  python manage.py collectstatic --noinput --clear
"

echo "Deploy thành công, giao diện đã được cập nhật!"

# 10. Chạy migrate nếu có thay đổi cơ sở dữ liệu
echo "Chạy database migrations..."
python manage.py migrate

# 11. Collect static files (nếu thay đổi trong static files)
echo "Thu thập static files..."
python manage.py collectstatic --noinput --clear

# 12. Dừng Daphne nếu đang chạy
echo "Dừng Daphne nếu đang chạy..."
PID=$(ps aux | grep daphne | grep "$DJANGO_MODULE" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
  kill "$PID"
  echo "Đã dừng Daphne (PID $PID)"
else
  echo "Không tìm thấy Daphne đang chạy."
fi

# 13. Khởi động lại Daphne
echo "Khởi động lại Daphne..."
nohup daphne -b 0.0.0.0 -p 8001 $DJANGO_MODULE > "$LOG_FILE" 2>&1 &

# 14. Xác nhận quá trình hoàn tất
echo "Deploy thành công!"
