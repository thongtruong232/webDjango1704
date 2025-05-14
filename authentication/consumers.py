import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from authentication.mongodb import get_collection_handle
from datetime import datetime
import pytz
import logging
from authentication.models import EmployeeTextNow

logger = logging.getLogger(__name__)

class UserActivityConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            await self.channel_layer.group_add("user_activity", self.channel_name)
            await self.accept()
            logger.info(f"WebSocket connected: {self.channel_name}")
            await self.send_initial_status()
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard("user_activity", self.channel_name)
            logger.info(f"WebSocket disconnected: {self.channel_name}")
        except Exception as e:
            logger.error(f"Error in WebSocket disconnect: {str(e)}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'get_initial_status':
                await self.send_initial_status()
        except json.JSONDecodeError:
            pass

    async def activity_status(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_user_status(self):
        try:
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                return []

            users = list(users_collection.find({}, {
                'user_id': 1,
                'username': 1,
                'is_active': 1,
                'last_activity': 1,
                'last_login': 1,
                'last_logout': 1
            }))

            work_time_collection = client['work_time']['stats']
            statuses = []

            for user in users:
                latest_session = work_time_collection.find_one(
                    {'user_id': user['user_id']},
                    sort=[('login_time', -1)]
                )

                session_data = {
                    'login_time': latest_session.get('login_time') if latest_session else None,
                    'logout_time': latest_session.get('logout_time') if latest_session else None,
                    'duration': latest_session.get('duration_str') if latest_session else None,
                    'session_id': latest_session.get('session_id') if latest_session else None
                }

                statuses.append({
                    'type': 'status_update',
                    'user_id': user['user_id'],
                    'is_active': user.get('is_active', False),
                    'username': user.get('username', ''),
                    'last_activity': user.get('last_activity', ''),
                    'last_login': user.get('last_login', ''),
                    'last_logout': user.get('last_logout', ''),
                    'session': session_data
                })

            return statuses
        except Exception as e:
            logger.error(f"Error getting user status: {str(e)}")
            return []
        finally:
            if 'client' in locals():
                try:
                    client.close()
                except Exception as e:
                    logger.error(f"Error closing MongoDB connection: {str(e)}")

    async def send_initial_status(self):
        statuses = await self.get_user_status()
        # Convert datetime objects to ISO format strings
        for status in statuses:
            if isinstance(status.get('last_activity'), datetime):
                status['last_activity'] = status['last_activity'].isoformat()
            if isinstance(status.get('last_login'), datetime):
                status['last_login'] = status['last_login'].isoformat()
            if isinstance(status.get('last_logout'), datetime):
                status['last_logout'] = status['last_logout'].isoformat()
            if status.get('session'):
                session = status['session']
                if isinstance(session.get('login_time'), datetime):
                    session['login_time'] = session['login_time'].isoformat()
                if isinstance(session.get('logout_time'), datetime):
                    session['logout_time'] = session['logout_time'].isoformat()

        await self.send(text_data=json.dumps({
            'type': 'initial_status',
            'statuses': statuses
        }))

class CreatedByConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # Gửi danh sách ban đầu
        await self.send_created_by_list()
        
    @database_sync_to_async
    def get_created_by_list(self):
        return list(EmployeeTextNow.objects.values_list('created_by', flat=True).distinct())
        
    async def send_created_by_list(self):
        created_by_list = await self.get_created_by_list()
        await self.send(text_data=json.dumps({
            'type': 'created_by_list',
            'created_by_list': created_by_list
        })) 