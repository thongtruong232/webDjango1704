from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import random
import logging
from authentication.permissions import role_required

logger = logging.getLogger(__name__)

@role_required(['admin', 'quanly', 'kiemtra', 'nhanvien'])
@csrf_exempt
@require_http_methods(["GET"])
def get_random_phones_message(request):
    try:
        quantity = int(request.GET.get('quantity', 1))
        if quantity < 1:
            quantity = 1
        elif quantity > 5:
            quantity = 5

        with open('area_phones.json', 'r', encoding='utf-8') as f:
            phones_data = json.load(f)
            random_phones = random.sample(phones_data['area_phones'], min(quantity, len(phones_data['area_phones'])))
            phone_numbers = [phone['phone_number'] for phone in random_phones]

        return JsonResponse({
            'success': True,
            'data': phone_numbers
        })
    except Exception as e:
        logger.error(f"Error in get_random_phones_message: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500) 