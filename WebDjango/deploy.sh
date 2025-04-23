#!/bin/bash

# === CONFIGURATION ===
PROJECT_DIR="/WebDjango"              # Thư mục chứa dự án Django (theo cấu trúc của bạn)
VENV_DIR="/WebDjango/venv"            # Thư mục chứa virtualenv (nếu có)
DJANGO_MODULE="WebDjango.asgi:application"  # Module ASGI của dự án
BRANCH="main"                         # Nhánh Git bạn sử dụng (có thể là 'main', 'master' hoặc nhánh khác)

# === DEPLOY PROCESS ===
echo "🔧 Bắt đầu quá trình deploy..."

# 1. Chuyển đến thư mục dự án
cd $PROJECT_DIR || exit

# 2. Kích hoạt virtualenv
echo "✅ Kích hoạt virtualenv..."
source $VENV_DIR/bin/activate

# 3. Lấy mã nguồn mới nhất từ Git repository
echo "📦 Cập nhật mã nguồn từ Git repository..."
git fetch origin
git reset --hard origin/$BRANCH

#  Build lại Docker image
echo "🔧 Build lại Docker image..."
docker compose build
# Dừng và xóa các container cũ + volume (static, cache...)
echo "🧹 Dọn dẹp container cũ..."
docker compose down -v
# Khởi động lại toàn bộ hệ thống
echo "🚀 Khởi động lại hệ thống..."
docker compose up -d
# Chờ vài giây để Django container sẵn sàng
echo "⏳ Chờ container sẵn sàng..."
sleep 5
# Cài đặt các gói mới (nếu có thay đổi trong requirements.txt)
echo "📥 Cài đặt dependencies mới..."
pip install -r requirements.txt
# Chạy migrate & collectstatic bên trong container
echo "🧩 Chạy migrate và thu thập static files..."
docker compose exec $PROJECT_NAME bash -c "
  python manage.py migrate &&
  python manage.py collectstatic --noinput
"

echo "✅ Deploy thành công, giao diện đã được cập nhật!"

# 5. Chạy migrate nếu có thay đổi cơ sở dữ liệu
echo "🧩 Chạy database migrations..."
python manage.py migrate

# 6. Collect static files (nếu thay đổi trong static files)
echo "🖼️ Thu thập static files..."
python manage.py collectstatic --noinput

# 7. Dừng Daphne nếu đang chạy
echo "🛑 Dừng Daphne nếu đang chạy..."
PID=$(ps aux | grep daphne | grep "$DJANGO_MODULE" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
  kill "$PID"
  echo "✅ Đã dừng Daphne (PID $PID)"
else
  echo "⚠️ Không tìm thấy Daphne đang chạy."
fi

# 8. Khởi động lại Daphne
echo "🚀 Khởi động lại Daphne..."
nohup daphne -b 0.0.0.0 -p 8001 $DJANGO_MODULE > daphne.log 2>&1 &

# 9. Xác nhận quá trình hoàn tất
echo "✅ Deploy thành công!"
