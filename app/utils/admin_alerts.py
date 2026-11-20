"""Admin ko alert: naya vendor register, naya dispute, waghera.

Active superusers ko in-app notification milti hai (aur Notification.send ki settings ke mutabiq email/push).
Yeh kabhi asli kaam (register / dispute) ko nahi rokta: koi bhi galti sirf log mein jati hai.
"""
import logging

logger = logging.getLogger(__name__)


def alert_admins(title, message, link=None, kind='warning', category='system'):
    """Wapas: kitne admins ko bheja."""
    sent = 0
    try:
        from django.contrib.auth.models import User
        from ..models import Notification
        for user in User.objects.filter(is_superuser=True, is_active=True):
            try:
                Notification.send(user=user, title=title, message=message,
                                  notification_type=kind, category=category, link=link)
                sent += 1
            except Exception:
                logger.exception('admin alert failed for user %s', user.pk)
    except Exception:
        logger.exception('admin alert failed: %s', title)
    return sent


def notify_admins(event, ctx=None, link=None, **overrides):
    """Template (app/utils/notification_rules.py) se admins ko notification: priority, category, grouping sab
    template se. Wapas: kitne admins ko bheja. Kabhi asli kaam ko nahi rokta."""
    sent = 0
    try:
        from django.contrib.auth.models import User
        from ..models import Notification
        for user in User.objects.filter(is_superuser=True, is_active=True):
            try:
                Notification.notify(event, user, ctx, link=link, **overrides)
                sent += 1
            except Exception:
                logger.exception('admin notify failed for user %s (%s)', user.pk, event)
    except Exception:
        logger.exception('admin notify failed: %s', event)
    return sent
