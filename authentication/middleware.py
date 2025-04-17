import uuid
import logging
from django.utils import timezone
from django.core.cache import cache
from .models import UserActivity

logger = logging.getLogger(__name__)

class ActivityTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # Xử lý trước khi request được xử lý
            if request.user.is_authenticated:
                session_id = request.session.get('activity_session_id')
                
                if session_id:
                    try:
                        # Cập nhật last_activity
                        updated = UserActivity.objects.filter(
                            session_id=session_id,
                            user=request.user,
                            logout_time__isnull=True
                        ).update(last_activity=timezone.now())
                        
                        if not updated:
                            # Nếu không tìm thấy session hiện tại, tạo mới
                            session_id = str(uuid.uuid4())
                            request.session['activity_session_id'] = session_id
                            self._create_activity(request, session_id)
                    except Exception as e:
                        logger.error(f'Error updating activity: {str(e)}')
                        # Tạo session mới nếu có lỗi
                        session_id = str(uuid.uuid4())
                        request.session['activity_session_id'] = session_id
                        self._create_activity(request, session_id)
                else:
                    # Tạo session ID mới nếu chưa có
                    session_id = str(uuid.uuid4())
                    request.session['activity_session_id'] = session_id
                    self._create_activity(request, session_id)
                    
                # Lưu session để đảm bảo session_id được lưu
                request.session.save()
                
        except Exception as e:
            logger.error(f'Error in ActivityTrackingMiddleware: {str(e)}')
            
        response = self.get_response(request)

        # Xử lý sau khi request được xử lý
        if request.user.is_authenticated:
            # Cập nhật cache user data
            cache_key = f'user_data_{request.user.id}'
            if not cache.get(cache_key):
                from .views import get_collection_handle
                users_collection, client = get_collection_handle('users')
                if users_collection:
                    user_data = users_collection.find_one({'user_id': str(request.user.id)})
                    if user_data:
                        cache.set(cache_key, user_data, timeout=300)  # Cache 5 phút
                    if client:
                        client.close()

        return response
        
    def _create_activity(self, request, session_id):
        try:
            # Tạo activity mới
            activity = UserActivity(
                user=request.user,
                session_id=session_id,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                login_time=timezone.now()
            )
            
            # Lưu thông tin thiết bị
            device_info = {
                'platform': request.META.get('HTTP_SEC_CH_UA_PLATFORM'),
                'browser': request.META.get('HTTP_USER_AGENT'),
                'mobile': request.META.get('HTTP_SEC_CH_UA_MOBILE', 'false') == 'true'
            }
            activity.set_device_info(device_info)
            activity.save()
            logger.info(f'Created new activity for user {request.user.username} with session {session_id}')
        except Exception as e:
            logger.error(f'Error creating activity: {str(e)}') 