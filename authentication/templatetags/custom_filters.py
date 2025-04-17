from django import template
import re

register = template.Library()

@register.filter
def format_duration(duration_str):
    # Sử dụng regex để lấy phần giờ:phút:giây
    match = re.match(r'(\d+:\d+:\d+)', str(duration_str))
    if match:
        return match.group(1)
    return duration_str 