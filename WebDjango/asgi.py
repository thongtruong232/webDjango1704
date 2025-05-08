"""
ASGI config for WebDjango project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path
from django.conf import settings

# Thiết lập Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'WebDjango.settings')
django.setup()

# Lấy ASGI application
django_asgi_app = get_asgi_application()

# Import consumers sau khi Django đã được thiết lập
from chat.consumers import ChatConsumer
from notification.consumers import NotificationConsumer

# Định nghĩa routing cho WebSocket
websocket_urlpatterns = [
    path('ws/chat/', ChatConsumer.as_asgi()),
    path('ws/notifications/', NotificationConsumer.as_asgi()),
]

# Tạo ASGI application với routing
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
