"""Rider in-app navigation: route lookup + turn-by-turn text.

Kaise chalta hai:
  1. Rider ka phone apni GPS position server ko bhejta hai (rider_nav_route).
  2. Server OSRM se route mangta hai (rider ke browser se direct nahi, taake CSP / API key / rate limit
     ek hi jagah rahe) aur chhota sa JSON wapas deta hai: line, steps, doori, waqt.
  3. Phone par map + agla mor + awaaz ka kaam browser karta hai (templates/customer_portal/rider/navigate.html).

Settings (optional):
  RIDER_NAV_OSRM_URL      default https://router.project-osrm.org  (demo server - sirf test ke liye;
                          production mein apna OSRM ya koi paid routing service lagayen)
  RIDER_NAV_TIMEOUT       seconds, default 6

Is module mein Django ke import function ke andar hain taake logic bina Django ke test ho sake.
"""
import json
import math
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_OSRM_URL = 'https://router.project-osrm.org'
DEFAULT_TIMEOUT = 6
CACHE_SECONDS = 20
MAX_POINTS = 1500          # line ke itne se zyada points hon to kam kar dete hain (phone ke liye halka)
MAX_STEPS = 80
MIN_FETCH_GAP_SECONDS = 5  # ek rider ki do route requests ke beech kam az kam itna waqt
# Batch (multi-stop) route: lambi line / zyada steps
MAX_POINTS_BATCH = 3000
MAX_STEPS_BATCH = 240
MAX_BATCH_POINTS = 10      # rider + zyada se zyada 9 stops (OSRM public server ki hadd ke andar)
BATCH_CACHE_SECONDS = 15


class NavError(Exception):
    """User-facing error (message rider ko dikha sakte hain)."""


# ---------------- coordinates ----------------

def valid_point(lat, lng):
    """Do values ko (float, float) banata hai ya NavError."""
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        raise NavError('Your location is not available yet.')
    if not (math.isfinite(la) and math.isfinite(ln)) or not (-90 <= la <= 90 and -180 <= ln <= 180):
        raise NavError('Your location is not valid.')
    if la == 0 and ln == 0:
        raise NavError('Your location is not available yet.')
    return la, ln


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------- current leg (store ya customer) ----------------

def leg_dest(di):
    """Rider ab kahan ja raha hai: 'assigned' = store, uske baad = customer.

    Return: {'leg','name','addr','lat','lng'} (lat/lng None ho sakte hain agar location save nahi)."""
    from . import dispatch, store_orders
    o = di.sale_order
    if di.status == 'assigned':
        lat, lng = dispatch._store_coords(o)
        vendor = o.vendor if o.vendor_id else None
        return {'leg': 'store', 'name': store_orders.store_name(o.vendor_id) if o.vendor_id else 'Store',
                'addr': getattr(vendor, 'address', '') or '', 'lat': lat, 'lng': lng}
    cust = o.customer
    lat = float(o.delivery_lat) if o.delivery_lat is not None else None
    lng = float(o.delivery_lng) if o.delivery_lng is not None else None
    return {'leg': 'customer', 'name': getattr(cust, 'name', '') or 'Customer',
            'addr': getattr(cust, 'address', '') or '', 'lat': lat, 'lng': lng}


# ---------------- turn text ----------------

MOD_TEXT = {
    'left': 'left', 'right': 'right',
    'slight left': 'slightly left', 'slight right': 'slightly right',
    'sharp left': 'sharp left', 'sharp right': 'sharp right',
    'straight': 'straight',
}

# Banner ke liye arrow (emoji) - modifier ke hisaab se
ARROWS = {
    'left': '⬅️', 'right': '➡️', 'slight left': '↖️', 'slight right': '↗️',
    'sharp left': '↙️', 'sharp right': '↘️', 'straight': '⬆️', 'uturn': '↩️',
}


def arrow(step_type, modifier):
    if step_type == 'arrive':
        return '🏁'
    if step_type in ('roundabout', 'rotary', 'roundabout turn', 'exit roundabout', 'exit rotary'):
        return '🔄'
    return ARROWS.get(modifier, '⬆️')


AR_MOD = {
    'left': 'يسارًا', 'right': 'يمينًا',
    'slight left': 'قليلًا إلى اليسار', 'slight right': 'قليلًا إلى اليمين',
    'sharp left': 'بشدة إلى اليسار', 'sharp right': 'بشدة إلى اليمين',
    'straight': 'للأمام',
}


def _instruction_ar(step):
    """Arabic turn text (Bahrain riders ke liye awaaz + banner)."""
    m = step.get('maneuver') or {}
    t = m.get('type') or ''
    mod = m.get('modifier') or ''
    name = (step.get('name') or '').strip()
    onto = f' إلى {name}' if name else ''
    if t == 'depart':
        return 'ابدأ' + (f' على {name}' if name else '')
    if t == 'arrive':
        side = {'left': ' على يسارك', 'right': ' على يمينك'}.get(mod, '')
        return 'لقد وصلت' + side
    if t in ('roundabout', 'rotary'):
        ex = m.get('exit')
        return f'عند الدوار، اتجه إلى المخرج {ex}{onto}' if ex else f'ادخل الدوار{onto}'
    if t in ('exit roundabout', 'exit rotary'):
        return f'اخرج من الدوار{onto}'
    if mod == 'uturn':
        return 'قم بالدوران للخلف' + onto
    word = AR_MOD.get(mod)
    if t == 'fork' and word:
        return f'ابقَ {word} عند التفرع{onto}'
    if t in ('off ramp', 'on ramp') and word:
        return f'خذ المنحدر {word}{onto}'
    if t == 'merge':
        return f'اندمج{onto}'
    if t in ('continue', 'new name') or mod == 'straight':
        return f'تابع بشكل مستقيم{onto}'
    if word:
        return f'انعطف {word}{onto}'
    return f'تابع{onto}'


def instruction(step, lang='en'):
    """OSRM step -> chhota jumla (OSRM khud text nahi deta). lang: 'en' (default) ya 'ar'."""
    if lang == 'ar':
        return _instruction_ar(step)
    m = step.get('maneuver') or {}
    t = m.get('type') or ''
    mod = m.get('modifier') or ''
    name = (step.get('name') or '').strip()
    onto = f' onto {name}' if name else ''
    if t == 'depart':
        return 'Start' + (f' on {name}' if name else '')
    if t == 'arrive':
        side = {'left': ' on your left', 'right': ' on your right'}.get(mod, '')
        return 'You have arrived' + side
    if t in ('roundabout', 'rotary'):
        ex = m.get('exit')
        return f'At the roundabout, take exit {ex}{onto}' if ex else f'Enter the roundabout{onto}'
    if t in ('exit roundabout', 'exit rotary'):
        return f'Exit the roundabout{onto}'
    if mod == 'uturn':
        return 'Make a U-turn' + onto
    word = MOD_TEXT.get(mod)
    if t == 'fork' and word:
        return f'Keep {word} at the fork{onto}'
    if t in ('off ramp', 'on ramp') and word:
        return f'Take the ramp on the {word}{onto}'
    if t == 'merge':
        return f'Merge{onto}'
    if t in ('continue', 'new name') or mod == 'straight':
        return f'Continue straight{onto}'
    if word:
        return f'Turn {word}{onto}'
    return f'Continue{onto}'


# ---------------- OSRM ----------------

def _base_url():
    from django.conf import settings
    return (getattr(settings, 'RIDER_NAV_OSRM_URL', '') or DEFAULT_OSRM_URL).rstrip('/')


def route_url(base, frm, to):
    """OSRM route URL. OSRM ke coordinates 'lng,lat' ki tarteeb mein hote hain."""
    return points_url(base, [frm, to])


def points_url(base, points):
    """Do ya zyada points (lat, lng) se guzarne wala OSRM route URL (batch ke liye)."""
    coords = ';'.join(f'{p[1]:.6f},{p[0]:.6f}' for p in points)
    return (f'{base}/route/v1/driving/{coords}'
            '?overview=full&geometries=geojson&steps=true&alternatives=false')


def _thin(points, limit=MAX_POINTS):
    if len(points) <= limit:
        return points
    stride = math.ceil(len(points) / limit)
    out = points[::stride]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


MANDATORY_STEPS = ('depart', 'arrive')


def cap_steps(steps, limit):
    """Steps limit se zyada hon to darmiyan ke chhote steps hata do; depart/arrive hamesha rehte hain.

    (Pehle sirf aakhri step rakh kar baqi kaat diye jate the - lambe batch route mein beech ke mor gum ho jate.)"""
    if len(steps) <= limit:
        return steps
    must = {i for i, s in enumerate(steps) if s['type'] in MANDATORY_STEPS}
    room = max(0, limit - len(must))
    minor = {'continue', 'new name', 'notification', 'merge'}
    optional = [i for i, s in enumerate(steps) if i not in must]
    keep = [i for i in optional if steps[i]['type'] not in minor][:room]
    if len(keep) < room:
        keep += [i for i in optional if steps[i]['type'] in minor][:room - len(keep)]
    chosen = sorted(must | set(keep))
    return [steps[i] for i in chosen]


def parse_route(data, lang='en', max_points=MAX_POINTS, max_steps=MAX_STEPS):
    """OSRM JSON -> {'distance_m','duration_s','line':[[lat,lng]..],'steps':[...],'legs':[...]} ya NavError.

    legs: har waypoint tak ka hissa {'distance_m','duration_s','end_m'} (end_m = shuru se is leg ke aakhir tak).
    Har step mein 'leg' (kaun se leg ka hissa) bhi hota hai."""
    if not isinstance(data, dict) or data.get('code') != 'Ok' or not data.get('routes'):
        raise NavError('No route found to this destination.')
    r = data['routes'][0]
    coords = ((r.get('geometry') or {}).get('coordinates')) or []
    line = [[round(c[1], 6), round(c[0], 6)] for c in coords if isinstance(c, (list, tuple)) and len(c) >= 2]
    if len(line) < 2:
        raise NavError('No route found to this destination.')
    steps, legs, start_m = [], [], 0.0
    for li, leg in enumerate(r.get('legs') or []):
        for st in leg.get('steps') or []:
            m = st.get('maneuver') or {}
            loc = m.get('location') or [None, None]
            dist = float(st.get('distance') or 0)
            steps.append({
                'text': instruction(st, lang), 'type': m.get('type') or '', 'mod': m.get('modifier') or '',
                'arrow': arrow(m.get('type') or '', m.get('modifier') or ''),
                'start_m': round(start_m), 'dist_m': round(dist),
                'lat': loc[1], 'lng': loc[0], 'leg': li,
                'name': (st.get('name') or '').strip(),
            })
            start_m += dist
        legs.append({'distance_m': round(float(leg.get('distance') or 0)),
                     'duration_s': round(float(leg.get('duration') or 0)), 'end_m': round(start_m)})
    return {
        'distance_m': round(float(r.get('distance') or 0)),
        'duration_s': round(float(r.get('duration') or 0)),
        'line': _thin(line, max_points),
        'steps': cap_steps(steps, max_steps),
        'legs': legs,
    }


def _bases():
    """Primary routing server + optional fallback (settings.RIDER_NAV_OSRM_FALLBACK_URL)."""
    from django.conf import settings
    out = [_base_url()]
    fb = (getattr(settings, 'RIDER_NAV_OSRM_FALLBACK_URL', '') or '').rstrip('/')
    if fb and fb not in out:
        out.append(fb)
    return out


def _request_json(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': 'rider-nav/1.0', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise NavError('Navigation is busy. Please try again in a moment.')
        raise NavError('Navigation service is not available right now.')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise NavError('Navigation service is not available right now.')


def _fetch(points, timeout, lang, max_points, max_steps):
    """Primary server fail ho to fallback server par koshish; 'no route' par dobara koshish nahi."""
    from django.conf import settings
    timeout = timeout or getattr(settings, 'RIDER_NAV_TIMEOUT', DEFAULT_TIMEOUT)
    last = None
    for base in _bases():
        try:
            data = _request_json(points_url(base, points), timeout)
        except NavError as exc:
            last = exc
            continue
        return parse_route(data, lang, max_points, max_steps)
    raise last or NavError('Navigation service is not available right now.')


def fetch_route(frm, to, timeout=None, lang='en'):
    """frm, to: (lat, lng). Short cache; network ya service ki kharabi par NavError."""
    from django.core.cache import cache
    key = 'rider_nav_route:%s:%.4f,%.4f:%.4f,%.4f' % (lang, frm[0], frm[1], to[0], to[1])
    hit = cache.get(key)
    if hit is not None:
        return hit
    route = _fetch([frm, to], timeout, lang, MAX_POINTS, MAX_STEPS)
    cache.set(key, route, CACHE_SECONDS)
    return route


def fetch_multi(points, timeout=None, lang='en'):
    """Batch route: points = [rider, stop1, stop2, ...] (lat, lng). Ek hi request mein poora raasta."""
    from django.core.cache import cache
    if len(points) < 2:
        raise NavError('No route found to this destination.')
    if len(points) > MAX_BATCH_POINTS:
        raise NavError('Too many stops for one route.')
    key = 'rider_nav_multi:%s:%s' % (lang, ';'.join('%.4f,%.4f' % (p[0], p[1]) for p in points))
    hit = cache.get(key)
    if hit is not None:
        return hit
    route = _fetch(points, timeout, lang, MAX_POINTS_BATCH, MAX_STEPS_BATCH)
    cache.set(key, route, BATCH_CACHE_SECONDS)
    return route
