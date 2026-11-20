"""Platform riders ki delivery fee/time (admin ki Delivery Settings se).

Jin stores ka `delivery_by == 'platform'` hai unki fee aur time yahin se aati hai.
Cache 2 minute; admin settings save karne par DeliverySettings.save() cache khud saaf karta hai.
"""
from decimal import Decimal

from django.core.cache import cache

CACHE_KEY = 'platform_delivery'

DEFAULTS = {
    'fee': Decimal('50'),
    'per_km': Decimal('0'),
    'free_radius_km': Decimal('0'),
    'time_min': 30,
    'time_max': 45,
}


def get_platform_delivery():
    data = cache.get(CACHE_KEY)
    if data is not None:
        return data
    data = dict(DEFAULTS)
    try:
        from ..models import DeliverySettings
        obj = DeliverySettings.objects.filter(is_active=True).first()
        if obj:
            data = {
                'fee': Decimal(obj.platform_delivery_fee or 0),
                'per_km': Decimal(obj.platform_fee_per_km or 0),
                'free_radius_km': Decimal(obj.platform_free_radius_km or 0),
                'time_min': int(obj.platform_time_min or DEFAULTS['time_min']),
                'time_max': int(obj.platform_time_max or DEFAULTS['time_max']),
            }
    except Exception:
        data = dict(DEFAULTS)
    cache.set(CACHE_KEY, data, 120)
    return data
