"""Rider support chat: rider <-> admin (ek rider ka ek hi thread).

Rider "Help" tab se admin ko likhta hai; admin Riders > Support se jawab deta hai. Naya paigham aane par samne wale
ko notification (2 minute mein ek dafa). Switch: Settings > Riders > "Rider support chat".
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_LEN = 1000
MAX_PER_MINUTE = 20
NOTIFY_GAP_MINUTES = 2
LIMIT = 200


class SupportError(Exception):
    """User ko seedha dikhai ja sakne wali ghalti."""


def clean_text(raw):
    text = str(raw or '').strip()
    if not text:
        raise SupportError('Write a message first.')
    if len(text) > MAX_LEN:
        raise SupportError(f'Message is too long (max {MAX_LEN} characters).')
    return text


def serialize(msg, my_role):
    local = timezone.localtime(msg.created_at)
    return {'id': msg.pk, 'mine': msg.sender_role == my_role, 'text': msg.message,
            'time': local.strftime('%I:%M %p').lstrip('0'), 'day': local.strftime('%d %b')}


def fetch(rider, after=0):
    qs = rider.support_messages.all()
    if after:
        return list(qs.filter(pk__gt=after).order_by('id')[:LIMIT])
    return list(qs.order_by('-id')[:LIMIT])[::-1]


def mark_read(rider, role):
    """role = kaun parh raha hai ('rider' ya 'admin')."""
    if role == 'rider':
        rider.support_messages.filter(sender_role='admin', is_read=False).update(is_read=True)
    else:
        rider.support_messages.filter(sender_role='rider', is_read=False).update(is_read=True)


def unread_for_rider(rider):
    return rider.support_messages.filter(sender_role='admin', is_read=False).count()


def unread_for_admin():
    from ..models import RiderSupportMessage
    return RiderSupportMessage.objects.filter(sender_role='rider', is_read=False).count()


def send(rider, role, user, raw_text):
    from ..models import RiderSupportMessage
    text = clean_text(raw_text)
    since = timezone.now() - timedelta(minutes=1)
    if RiderSupportMessage.objects.filter(rider=rider, sender=user, created_at__gte=since).count() >= MAX_PER_MINUTE:
        raise SupportError('Too many messages. Please wait a moment.')
    msg = RiderSupportMessage.objects.create(rider=rider, sender_role=role, sender=user, message=text)
    _notify(rider, role, text)
    return msg


def _notify(rider, sender_role, text):
    try:
        from django.contrib.auth.models import User
        from ..models import Notification
        from . import store_orders
        since = timezone.now() - timedelta(minutes=NOTIFY_GAP_MINUTES)
        if sender_role == 'rider':
            title = f'💬 Rider {rider.name}'
            link = f'/shop/rider/manage/support/{rider.pk}/'
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                if not Notification.objects.filter(user=admin, title=title, created_at__gte=since).exists():
                    store_orders._notify(admin, title, text[:140], link, 'info', category='riders')
        else:
            title = '💬 Support replied'
            if not Notification.objects.filter(user=rider.user, title=title, created_at__gte=since).exists():
                store_orders._notify(rider.user, title, text[:140], '/shop/rider/support/', 'info')
    except Exception:
        logger.exception('rider support notify failed')
