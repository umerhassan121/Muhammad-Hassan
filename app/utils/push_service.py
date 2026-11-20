"""
Web Push bhejne ka kaam (phone/browser par popup, chahe site band ho).

Setup (ek baar):
  1. pip install pywebpush
  2. python manage.py generate_vapid_keys      -> 2 keys print karta hai
  3. Un keys ko settings.py (ya environment) mein rakhein:
        VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CONTACT_EMAIL
Keys ya pywebpush na ho to ye module chupchap kuch nahi karta (order/notification kabhi nahi rukte).
Push sirf HTTPS par (ya localhost par) chalta hai.
"""
import json
import logging
import os
import threading

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def _cfg(name):
    return (getattr(settings, name, None) or os.environ.get(name) or '').strip()


def public_key():
    return _cfg('VAPID_PUBLIC_KEY')


def is_configured():
    if not (_cfg('VAPID_PUBLIC_KEY') and _cfg('VAPID_PRIVATE_KEY')):
        return False
    try:
        import pywebpush  # noqa: F401
    except Exception:
        return False
    return True


def _enabled():
    try:
        from app.shop_flags import shop_flag
        return bool(shop_flag('shop_push_enabled'))
    except Exception:
        return True


def _deliver(subs, payload, urgent=False):
    """Alag thread mein (order/notification ko dheema na kare).
    urgent=True (vendor/rider ka naya order): push service ko 'high' urgency batata hai (doze mode mein bhi jaldi pahunche)
    aur ttl chhota rakhta hai (purana 'naya order' alert baad mein bekaar hota hai)."""
    from django.db import connection
    from django.utils import timezone
    try:
        from pywebpush import WebPushException, webpush
        from app.models import PushSubscription
        private = _cfg('VAPID_PRIVATE_KEY')
        contact = _cfg('VAPID_CONTACT_EMAIL') or 'admin@example.com'
        for s in subs:
            try:
                webpush(
                    subscription_info={'endpoint': s['endpoint'], 'keys': {'p256dh': s['p256dh'], 'auth': s['auth']}},
                    data=payload,
                    vapid_private_key=private,
                    vapid_claims={'sub': f'mailto:{contact}'},   # pywebpush dict badal deta ha, har baar naya
                    ttl=600 if urgent else 3600,
                    headers={'Urgency': 'high'} if urgent else None,
                )
                PushSubscription.objects.filter(pk=s['id']).update(last_success_at=timezone.now())
            except WebPushException as exc:
                code = getattr(getattr(exc, 'response', None), 'status_code', None)
                if code in (404, 410):          # browser ne subscription khatam kar di
                    PushSubscription.objects.filter(pk=s['id']).delete()
                else:
                    logger.warning('Push failed (%s): %s', code, exc)
            except Exception as exc:
                logger.warning('Push error: %s', exc)
    except Exception as exc:
        logger.error('Push delivery error: %s', exc)
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ---- Push ka "profile": kaun sa portal, kitni zaroori, vibration, buttons ----------------------------
# Notification.send(..., link=...) se khud pehchana jata hai (purane call sites badalne ki zaroorat nahi).
# Ya Notification.send(..., push_kind='rider', push_actions=[...]) se zabardasti set karein.
_VIBRATE = {
    'vendor': [400, 150, 400, 150, 400],   # lamba: kitchen/dukaan ke shor mein bhi mehsoos ho
    'rider':  [300, 100, 300, 100, 300],
    'order':  [200, 100, 200],
    'investor': [120],
    'admin':  [150, 80, 150],
}


def _kind_for(url):
    u = url or ''
    if u.startswith('/shop/vendor/'):
        return 'vendor'
    if u.startswith('/shop/rider/'):
        return 'rider'
    if u.startswith(('/investor/', '/shareholder/', '/shareholders/portal/', '/transfers/', '/balance-dividend/')):
        return 'investor'
    if u.startswith('/shop/'):
        return 'order'
    return 'admin'


def _profile(url, kind=None, actions=None):
    """-> dict: kind, urgent, vibrate, interaction, actions (max 2), tag."""
    import time
    u = url or '/shop/'
    kind = kind or _kind_for(u)
    # Naya order alert: vendor ke orders page / rider ke home par bheja jata hai
    urgent = (kind == 'vendor' and u.split('?')[0] == '/shop/vendor/orders/' and '?' not in u) or \
             (kind == 'rider' and u == '/shop/rider/')
    if actions is None:
        if urgent:
            # Accept/Reject jaise buttons ke liye caller signed token wale actions deta hai (push_actions.py);
            # warna sirf "Open".
            actions = [{'action': 'open', 'title': 'Open orders' if kind == 'vendor' else 'Open', 'url': u}]
        elif kind == 'order' and u.startswith(('/shop/order/', '/shop/track/')):
            actions = [{'action': 'open', 'title': 'Track order', 'url': u},
                       {'action': 'orders', 'title': 'My orders', 'url': '/shop/my-orders/'}]
        elif kind in ('investor', 'admin', 'order'):
            actions = [{'action': 'open', 'title': 'Open', 'url': u}]
        else:
            actions = []
    clean = []
    oid = None
    for a in list(actions)[:2]:
        if isinstance(a, dict) and a.get('oid') and oid is None:
            oid = str(a['oid'])[:20]                     # Chrome/Android: sirf 2 buttons
        if isinstance(a, dict) and a.get('action') and a.get('title'):
            item = {'action': str(a['action'])[:30], 'title': str(a['title'])[:30]}
            if a.get('url') and str(a['url']).startswith('/'):   # sirf apni site ke raste
                item['url'] = str(a['url'])[:300]
            if a.get('token'):                                     # seedha action (push_actions.push_action)
                item['token'] = str(a['token'])[:600]
            clean.append(item)
    return {
        'kind': kind,
        'urgent': urgent,
        'vibrate': _VIBRATE.get(kind, [150]),
        'interaction': urgent,                                    # jab tak user dekhe nahi, notification rahe
        'actions': clean,
        # urgent: har order ka apna notification (reminder usi ko replace karta hai, awaaz dobara aati hai)
        'tag': ('%s-order-%s' % (kind, oid)) if (urgent and oid) else
               (('%s-%d' % (kind, int(time.time() * 1000))) if urgent else u),
    }


# ---- Native Android app (Capacitor + Firebase Cloud Messaging) -------------------------------------
# Setup: GitHub secret FIREBASE_SERVICE_ACCOUNT_BASE64 (service account JSON ka base64) + pip install firebase-admin.
# Na ho to ye hissa chupchap kuch nahi karta; Web Push pehle jaisa chalta rahta hai.
_FCM_APP = None


def _service_account_info():
    """Service account JSON (dict). Env: FIREBASE_SERVICE_ACCOUNT_BASE64 ya seedha FIREBASE_SERVICE_ACCOUNT_JSON."""
    import base64
    raw_json = _cfg('FIREBASE_SERVICE_ACCOUNT_JSON')
    if raw_json:
        return json.loads(raw_json)
    b64 = ''.join(_cfg('FIREBASE_SERVICE_ACCOUNT_BASE64').split()).strip('"')
    if not b64:
        return None
    return json.loads(base64.b64decode(b64).decode('utf-8'))


def fcm_is_configured():
    if not (_cfg('FIREBASE_SERVICE_ACCOUNT_BASE64') or _cfg('FIREBASE_SERVICE_ACCOUNT_JSON')):
        return False
    try:
        import firebase_admin  # noqa: F401
    except Exception:
        return False
    return True


def _fcm_app():
    """firebase_admin app (ek baar banta hai). Kharab key ho to None."""
    global _FCM_APP
    if _FCM_APP is not None:
        return _FCM_APP
    try:
        import firebase_admin
        from firebase_admin import credentials
        info = _service_account_info()
        if not info:
            return None
        _FCM_APP = firebase_admin.initialize_app(credentials.Certificate(info), name='shop-push')
        return _FCM_APP
    except Exception as exc:
        logger.error('FCM init error: %s', exc)
        return None


def fcm_action_data(title, body, url, prof):
    """Pure: sirf data wala FCM message (koi 'notification' block nahi) - APK ki RiderMessagingService isse
    Accept / Decline (vendor: Accept / Reject) buttons wali notification banati hai. Sirf unhi phones ko jate hain
    jin ki APK ye service rakhti hai (Rider aur Vendor APK dono)."""
    import json
    acts = []
    for a in (prof.get('actions') or [])[:2]:
        if isinstance(a, dict) and a.get('token') and a.get('action') and a.get('title'):
            acts.append({'action': str(a['action'])[:30], 'title': str(a['title'])[:30], 'token': str(a['token'])[:600]})
    return {
        'act': '1',
        'title': str(title)[:120],
        'body': str(body or '')[:300],
        'url': str(url or ('/shop/vendor/orders/' if prof.get('kind') == 'vendor' else '/shop/rider/'))[:300],
        'kind': str(prof.get('kind') or ''),
        'tag': str(prof.get('tag') or '')[:100],
        'actions': json.dumps(acts),
    }


def fcm_message_parts(title, body, url, prof):
    """Pure: (notification dict, data dict, android dict) - FCM message ke hisse (firebase ke bagair test ho sakta hai).
    urgent (naya order) -> 'orders' channel (high importance, awaaz) + ttl 10 min; baqi -> 'general' channel."""
    urgent = bool(prof.get('urgent'))
    notification = {'title': str(title)[:120], 'body': str(body or '')[:300]}
    data = {'url': str(url or '/shop/rider/')[:300], 'kind': str(prof.get('kind') or ''), 'tag': str(prof.get('tag') or '')[:100]}
    android = {
        'priority': 'high' if urgent else 'normal',
        'ttl_seconds': 600 if urgent else 3600,
        'channel_id': 'orders_v2' if urgent else 'general',   # orders_v2 = lambi ring (APK mein res/raw/order_ring.wav)
        'sound': 'order_ring' if urgent else 'default',
        'tag': str(prof.get('tag') or '')[:100] or None,
        'notification_count': prof.get('badge_count'),   # APK icon par number (launcher support par)
    }
    return notification, data, android


def devices_for_kind(kind, devices):
    """Pure: ek user ke Rider aur Vendor dono APK hon to vendor ki push sirf Vendor APK ko aur rider ki push sirf Rider APK ko.
    (admin / purani entries jin ka 'app' nahi, unhein pehle ki tarah har push milti hai.)"""
    if kind == 'order':          # customer ki push: Customer APK ho to Rider/Vendor APK ko na jaye
        if any(d.get('app') == 'customer' for d in devices):
            return [d for d in devices if d.get('app') not in ('rider', 'vendor')]
        return list(devices)
    other = {'vendor': 'rider', 'rider': 'vendor'}.get(kind)
    if not other:
        return [d for d in devices if d.get('app') != 'customer']   # Customer APK ko sirf customer (order) push
    return [d for d in devices if d.get('app') not in (other, 'customer')]


def _deliver_fcm(devices, title, body, url, prof):
    """Alag thread mein: native app ke tokens ko FCM push. Ghalat/purane token delete."""
    from datetime import timedelta
    from django.db import connection
    from django.utils import timezone
    try:
        from firebase_admin import messaging
        from app.models import FcmDevice
        app = _fcm_app()
        if app is None:
            return
        notification, data, android = fcm_message_parts(title, body, url, prof)
        # Naya order + signed token wale buttons: sirf data-only message (APK ki service buttons ke saath dikhati hai)
        action_data = None
        if prof.get('urgent') and prof.get('kind') in ('rider', 'vendor') and any(a.get('token') for a in (prof.get('actions') or [])):
            action_data = fcm_action_data(title, body, url, prof)
        for d in devices:
            try:
                if action_data and d.get('platform') == 'android-act':
                    msg = messaging.Message(
                        token=d['token'],
                        data=action_data,
                        android=messaging.AndroidConfig(priority='high', ttl=timedelta(seconds=android['ttl_seconds'])),
                    )
                else:
                    msg = messaging.Message(
                        token=d['token'],
                        notification=messaging.Notification(title=notification['title'], body=notification['body']),
                        data=data,
                        android=messaging.AndroidConfig(
                            priority=android['priority'],
                            ttl=timedelta(seconds=android['ttl_seconds']),
                            notification=messaging.AndroidNotification(
                                channel_id=android['channel_id'], sound=android['sound'], tag=android['tag'],
                                notification_count=android.get('notification_count')),
                        ),
                    )
                messaging.send(msg, app=app)
                FcmDevice.objects.filter(pk=d['id']).update(last_success_at=timezone.now())
            except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
                FcmDevice.objects.filter(pk=d['id']).delete()           # app uninstall / token badal gaya
            except Exception as exc:
                logger.warning('FCM push failed: %s', exc)
    except Exception as exc:
        logger.error('FCM delivery error: %s', exc)
    finally:
        try:
            connection.close()
        except Exception:
            pass


def send_push(user, title, body='', url=None, kind=None, actions=None):
    """User ke saare registered browsers/phones ko push (Web Push) aur native app ko (FCM). Kabhi exception nahi uthata."""
    try:
        if not user or not _enabled():
            return 0
        web_ok = is_configured()
        fcm_ok = fcm_is_configured()
        if not (web_ok or fcm_ok):
            return 0
        from app.models import FcmDevice, PushSubscription
        subs = list(PushSubscription.objects.filter(user=user).values('id', 'endpoint', 'p256dh', 'auth')) if web_ok else []
        devices = list(FcmDevice.objects.filter(user=user).values('id', 'token', 'platform', 'app')) if fcm_ok else []
        if not subs and not devices:
            return 0
        url = url or ('/notifications/' if getattr(user, 'is_staff', False) else '/shop/')   # link na ho to staff ko list
        prof = _profile(url, kind, actions)
        devices = devices_for_kind(prof['kind'], devices)
        if subs:
            payload = json.dumps({
                'title': str(title)[:120],
                'body': str(body or '')[:300],
                'url': url,
                'kind': prof['kind'],
                'tag': prof['tag'],
                'vibrate': prof['vibrate'],
                'interaction': prof['interaction'],
                'actions': prof['actions'],
            })
            threading.Thread(target=_deliver, args=(subs, payload, prof['urgent']), daemon=True).start()
        if devices:
            try:
                if prof['kind'] in ('rider', 'vendor'):
                    from app.customer.views_push import _badge_count
                    prof['badge_count'] = max(1, _badge_count(user, prof['kind']))
            except Exception:
                pass
            threading.Thread(target=_deliver_fcm, args=(devices, title, body, url, prof), daemon=True).start()
        return len(subs) + len(devices)
    except Exception as exc:
        logger.error('send_push error: %s', exc)
        return 0


def send_push_after_commit(user, title, body='', url=None, kind=None, actions=None):
    """Transaction mein bana order rollback ho jaye to push na jaye: commit ke baad bhejein."""
    try:
        transaction.on_commit(lambda: send_push(user, title, body, url, kind, actions))
    except Exception as exc:
        logger.error('send_push_after_commit error: %s', exc)
