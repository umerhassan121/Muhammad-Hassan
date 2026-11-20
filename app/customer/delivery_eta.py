"""Customer ko delivery ETA ("Rider 12 minute mein pahunchega").

Hisaab:
  * Rider abhi store ki taraf ('assigned'):  rider -> store  +  store -> customer  +  pickup ka waqt
  * Rider customer ki taraf (picked_up / in_transit):  rider -> customer
Har leg ka waqt routing (OSRM, rider_nav) se aata hai. Routing na chale to seedhi doori (road factor ke saath)
aur ausat raftar se andaza lagta hai (approx=True). ETA ki kharabi tracking ko kabhi nahi roakti.

Batch: agar rider ke paas 2-3 orders hain to is order se pehle wale stops (doosre store / customers) ka raasta aur
unke rukne ka waqt bhi ETA mein jurta hai - warna 2nd / 3rd customer ko ETA bohat kam dikhta tha.

Settings (optional):
  DELIVERY_ETA_ROUTING         True/False, default True (False = hamesha seedhi doori se andaza)
  DELIVERY_ETA_TRAFFIC_FACTOR  routing ke waqt par guna, default 1.15 (bike/traffic ka farq)
  DELIVERY_ETA_ROUTE_TIMEOUT   routing ka intezar (second), default 3

Is module mein Django ke import function ke andar hain taake logic bina Django ke test ho sake.
"""
import logging
import math

from . import rider_nav

log = logging.getLogger(__name__)

ROAD_FACTOR = 1.35          # seedhi doori -> sadak ki doori (andaza)
FALLBACK_SPEED_KMH = 22.0   # shehar mein bike ki ausat raftar (andaza)
PICKUP_BUFFER_SECONDS = 3 * 60   # store se order lene mein lagne wala waqt
DEFAULT_TRAFFIC_FACTOR = 1.15
ARRIVING_METERS = 120       # itni doori par "pahunchne wala hai"
CACHE_SECONDS = 45          # ek order ka ETA itni der cache (customer har 8 second poll karta hai)
BREAKER_SECONDS = 120       # routing fail ho to itni der dobara koshish nahi


def fallback_leg(a, b):
    """(seconds, meters) - bina routing ke andaza."""
    meters = rider_nav.haversine_m(a[0], a[1], b[0], b[1]) * ROAD_FACTOR
    return meters / (FALLBACK_SPEED_KMH * 1000 / 3600), meters


def build(total_seconds, dist_m, stage, approx, now=None):
    """Hisaab ke natije ko customer ke liye dict mein badalta hai.

    stage: 'pickup' (rider store ja raha hai) ya 'delivery' (rider customer ke paas aa raha hai)."""
    minutes = max(1, int(math.ceil(max(0.0, total_seconds) / 60.0)))
    out = {
        'minutes': minutes, 'stage': stage, 'dist_m': int(round(dist_m)), 'approx': bool(approx),
        'arriving': stage == 'delivery' and dist_m < ARRIVING_METERS,
        'clock': '',
    }
    if now is not None:
        from datetime import timedelta
        t = now + timedelta(minutes=minutes)
        out['clock'] = t.strftime('%I:%M %p').lstrip('0')
    return out


# ---------------- DB / routing wala hissa ----------------

def _traffic_factor():
    from django.conf import settings
    try:
        return float(getattr(settings, 'DELIVERY_ETA_TRAFFIC_FACTOR', DEFAULT_TRAFFIC_FACTOR))
    except (TypeError, ValueError):
        return DEFAULT_TRAFFIC_FACTOR


def _leg(a, b):
    """(seconds, meters, approx) ek leg ke liye: pehle routing, warna andaza."""
    from django.conf import settings
    from django.core.cache import cache
    if getattr(settings, 'DELIVERY_ETA_ROUTING', True) and not cache.get('deliv_eta_route_down'):
        try:
            r = rider_nav.fetch_route(a, b, timeout=getattr(settings, 'DELIVERY_ETA_ROUTE_TIMEOUT', 3))
            return r['duration_s'] * _traffic_factor(), float(r['distance_m']), False
        except rider_nav.NavError:
            cache.set('deliv_eta_route_down', 1, BREAKER_SECONDS)
    sec, meters = fallback_leg(a, b)
    return sec, meters, True


def batch_total(points, kinds, route_fn):
    """Pure hisaab: points = [rider, stop1, ...]; kinds = har stop ki qism ('pickup'/'drop').
    route_fn(a, b) -> (seconds, meters, approx). Return (seconds, meters, approx) - rukne ka waqt shamil."""
    from . import batch_nav
    total_s = total_m = 0.0
    approx = False
    for i in range(1, len(points)):
        sec, meters, ap = route_fn(points[i - 1], points[i])
        # points[i-1] ek stop hai (i >= 2) jahan rider ruka: uski qism kinds[i-2]
        total_s += sec + (batch_nav.dwell(kinds[i - 2]) if i > 1 else 0)
        total_m += meters
        approx = approx or ap
    return total_s, total_m, approx


def _batch_result(order, rider, me, stage):
    """Agar rider ke paas is order ke ilawa bhi active orders hain: is order ke drop tak poora raasta.
    Koi bhi masla ho (ya sirf ek order) to None - phir seedha ETA hi dikhta hai."""
    if getattr(rider, 'pk', None) is None:
        return None
    try:
        from . import batch_nav
        from django.utils import timezone
        data = batch_nav.build(rider, start=me)
        if len(data['infos']) < 2 or not data['plan']:
            return None
        stops = [s for s in data['plan']['stops'] if s['ll']]
        idx = batch_nav.stops_before(stops, order.pk)
        if idx is None or idx == 0:
            return None                       # pehle hi is order ka drop hai: seedha hisaab theek hai
        upto = stops[:idx + 1]
        pts = [me] + [s['ll'] for s in upto]
        kinds = [s['kind'] for s in upto]
        try:
            if not getattr(settings_mod(), 'DELIVERY_ETA_ROUTING', True) or cache_down():
                raise rider_nav.NavError('skip')
            r = rider_nav.fetch_multi(pts, timeout=getattr(settings_mod(), 'DELIVERY_ETA_ROUTE_TIMEOUT', 3))
            sec = r['duration_s'] * _traffic_factor()
            meters = float(r['distance_m'])
            for k in kinds[:-1]:
                sec += batch_nav.dwell(k)
            approx = False
        except rider_nav.NavError:
            sec, meters, approx = batch_total(pts, kinds, lambda a, b: (*fallback_leg(a, b), True))
        result = build(sec, meters, stage, approx, timezone.localtime())
        result['stops_before'] = idx
        return result
    except Exception:
        log.warning('batch ETA failed for order %s', getattr(order, 'pk', None), exc_info=True)
        return None


def settings_mod():
    from django.conf import settings
    return settings


def cache_down():
    from django.core.cache import cache
    return bool(cache.get('deliv_eta_route_down'))


def for_delivery(di, order, rider):
    """ETA dict ya None (location/pin na ho to). Cache: ek order ka 45 second."""
    from django.core.cache import cache
    from django.utils import timezone
    from . import dispatch

    if rider is None or rider.last_lat is None or rider.last_lng is None:
        return None
    if order.delivery_lat is None or order.delivery_lng is None:
        return None
    stage = 'pickup' if di.status == 'assigned' else 'delivery'
    key = f'deliv_eta:{order.pk}:{stage}'
    hit = cache.get(key)
    if hit is not None:
        return hit or None

    me = (float(rider.last_lat), float(rider.last_lng))
    drop = (float(order.delivery_lat), float(order.delivery_lng))
    result = _batch_result(order, rider, me, stage)
    if result is not None:
        cache.set(key, result, CACHE_SECONDS)
        return result
    if stage == 'pickup':
        s_lat, s_lng = dispatch._store_coords(order)
        if s_lat is None:
            cache.set(key, {}, CACHE_SECONDS)        # store ki location nahi: sahi ETA nahi ban sakti
            return None
        store = (s_lat, s_lng)
        s1, m1, a1 = _leg(me, store)
        s2, m2, a2 = _leg(store, drop)
        result = build(s1 + s2 + PICKUP_BUFFER_SECONDS, m1 + m2, stage, a1 or a2, timezone.localtime())
    else:
        s1, m1, a1 = _leg(me, drop)
        result = build(s1, m1, stage, a1, timezone.localtime())
    cache.set(key, result, CACHE_SECONDS)
    return result
