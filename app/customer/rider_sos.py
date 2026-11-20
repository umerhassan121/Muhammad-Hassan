"""Rider SOS: ek tap par admin ko foran alert (rider ka naam, phone, jagah, chalta hua order).

Emergency number: Bahrain mein 999 (police / ambulance). Doosre mulk ke liye EMERGENCY_NUMBER badlein."""
from django.utils import timezone

from . import rider_nav, store_orders

EMERGENCY_NUMBER = '999'
LAST_LOCATION_MAX_MIN = 30     # rider ki purani jagah is se purani ho to 'last' nahi mani jati


def open_alert(rider):
    return rider.sos_alerts.filter(status='open').first()


def _admins():
    from django.contrib.auth.models import User
    return User.objects.filter(is_superuser=True, is_active=True)


def _point(rider, lat, lng):
    """-> (lat, lng, source). Pehle phone se aayi jagah, warna rider ki aakhri jagah (agar taaza ho)."""
    try:
        la, ln = rider_nav.valid_point(lat, lng)
        return la, ln, 'live'
    except rider_nav.NavError:
        pass
    if rider.last_lat is not None and rider.last_lng is not None and rider.last_location_at:
        if (timezone.now() - rider.last_location_at).total_seconds() <= LAST_LOCATION_MAX_MIN * 60:
            return float(rider.last_lat), float(rider.last_lng), 'last'
    return None, None, ''


def map_url(alert):
    if alert.lat is None or alert.lng is None:
        return ''
    return f'https://www.google.com/maps?q={alert.lat},{alert.lng}'


def trigger(rider, lat=None, lng=None, note=''):
    """-> (alert, created). Pehle se khula alert ho to naya nahi banta (admin ko baar baar spam nahi)."""
    from ..models import DeliveryInfo, RiderSOS
    existing = open_alert(rider)
    if existing:
        return existing, False
    la, ln, src = _point(rider, lat, lng)
    di = (DeliveryInfo.objects.filter(rider=rider, status__in=('assigned', 'picked_up', 'in_transit'))
          .select_related('sale_order').order_by('-assigned_at').first())
    alert = RiderSOS.objects.create(rider=rider, delivery=di, lat=la, lng=ln, location_source=src,
                                    note=(note or '').strip()[:200])
    parts = [f'{rider.name} ({rider.phone}) pressed SOS.']
    if di and di.sale_order_id:
        parts.append(f'Active order #{di.sale_order.order_no}.')
    if alert.lat is not None:
        parts.append('Live location.' if src == 'live' else 'Last known location.')
    else:
        parts.append('Location not available - call the rider.')
    if alert.note:
        parts.append(alert.note)
    text = ' '.join(parts)
    for a in _admins():
        try:
            store_orders._notify(a, f'🆘 SOS: {rider.name}', text, '/shop/rider/manage/sos/', 'warning',
                                 category='riders', priority='high')
        except Exception:
            import logging
            logging.getLogger(__name__).exception('SOS notify failed')
    return alert, True


def resolve(alert, user, admin_note=''):
    if alert.status != 'open':
        return alert
    alert.status = 'resolved'
    alert.resolved_at = timezone.now()
    alert.resolved_by = user
    alert.admin_note = (admin_note or '').strip()[:200]
    alert.save(update_fields=['status', 'resolved_at', 'resolved_by', 'admin_note'])
    try:
        store_orders._notify(alert.rider.user, '✅ SOS closed', 'The admin closed your SOS alert. Stay safe!',
                             '/shop/rider/', 'success', category='riders')
    except Exception:
        pass
    return alert
