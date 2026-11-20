"""Shop ka default warehouse.

Vendor product add, customer signup aur customer checkout sab ek hi warehouse se stock chalate hain.
Agar database me koi warehouse na ho to "Main Warehouse" khud ban jata hai (vendor ko error nahi milta).
Pehle se warehouse maujood ho to wahi pehla (pehle jaisa) use hota hai.
"""
import logging

logger = logging.getLogger(__name__)

DEFAULT_WAREHOUSE_NAME = 'Main Warehouse'


def get_default_warehouse(create=True):
    from ..models import Warehouse
    wh = Warehouse.objects.first()
    if wh is not None or not create:
        return wh
    try:
        wh, _ = Warehouse.objects.get_or_create(
            name=DEFAULT_WAREHOUSE_NAME,
            defaults={'description': 'Auto-created default warehouse'},
        )
        logger.info('Default warehouse auto-created: %s', wh.name)
        return wh
    except Exception:
        logger.exception('Default warehouse create failed')
        return Warehouse.objects.first()
