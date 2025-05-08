#!/bin/bash

# === CONFIGURATION ===
PROJECT_DIR="/WebDjango"
DJANGO_MODULE="WebDjango.asgi:application"
PROJECT_NAME="webdjango"
COMPOSE_PROJECT_NAME="webdjango"  # Tên project cho docker-compose

# === DEPLOY PROCESS ===
echo "=== Bắt đầu quá trình deploy cho project $COMPOSE_PROJECT_NAME ==="

# 1. Chuyển đến thư mục dự án
cd $PROJECT_DIR || exit

# 2. Dừng và xóa các container của project hiện tại
echo "Dừng và xóa các container của project $COMPOSE_PROJECT_NAME..."
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME docker compose down

# 3. Xóa các volume chỉ của project hiện tại
echo "Xóa các volume của project $COMPOSE_PROJECT_NAME..."
docker volume rm ${COMPOSE_PROJECT_NAME}_static_volume ${COMPOSE_PROJECT_NAME}_redis_data ${COMPOSE_PROJECT_NAME}_mongodb_data 2>/dev/null || true

# 4. Xóa các image chỉ của project hiện tại
echo "Xóa các image của project $COMPOSE_PROJECT_NAME..."
docker rmi $(docker images -q ${COMPOSE_PROJECT_NAME}_web) 2>/dev/null || true

# 5. Build lại Docker image cho project hiện tại
echo "Build lại Docker image cho project $COMPOSE_PROJECT_NAME..."
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME docker compose build --no-cache

# 6. Khởi động lại toàn bộ hệ thống của project hiện tại
echo "Khởi động lại hệ thống cho project $COMPOSE_PROJECT_NAME..."
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME docker compose up -d

# 7. Chờ container sẵn sàng
echo "Chờ container sẵn sàng..."
sleep 10

# 8. Chạy migrate và collectstatic trong container của project hiện tại
echo "Chạy migrate và collectstatic cho project $COMPOSE_PROJECT_NAME..."
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME docker compose exec $PROJECT_NAME bash -c "
    python manage.py migrate --noinput &&
    python manage.py collectstatic --noinput
"

# 9. Kiểm tra logs của project hiện tại
echo "Kiểm tra logs của project $COMPOSE_PROJECT_NAME..."
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME docker compose logs --tail=50

echo "=== Deploy hoàn tất cho project $COMPOSE_PROJECT_NAME ==="
