from django.utils import timezone
from django.shortcuts import redirect
from django.conf import settings
from datetime import timedelta
import pytz

class AutoLogoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.inactivity_timeout = timedelta(minutes=60)  # 60 phút không hoạt động sẽ tự động logout

    def __call__(self, request):
        if request.user.is_authenticated:
            # Lấy thời gian hoạt động cuối cùng từ session
            last_activity = request.session.get('last_activity')
            if last_activity:
                last_activity = timezone.datetime.fromisoformat(last_activity)
                current_time = timezone.now()
                
                # Kiểm tra nếu đã quá thời gian không hoạt động
                if current_time - last_activity > self.inactivity_timeout:
                    # Xóa session và chuyển hướng về trang login
                    request.session.flush()
                    return redirect('login')
            
            # Cập nhật thời gian hoạt động cuối cùng
            request.session['last_activity'] = timezone.now().isoformat()
        
        response = self.get_response(request)
        return response 