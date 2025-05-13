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

@register.filter
def get_range(value):
    """
    Filter - returns a list containing range made from given value
    Usage (in template):
    <ul>{% for i in 3|get_range %}
      <li>{{ i }}. Do something</li>
    {% endfor %}</ul>
    """
    try:
        value = int(value)
        if value < 1:
            return range(1)
        return range(1, value + 1)
    except (ValueError, TypeError):
        return range(1) 