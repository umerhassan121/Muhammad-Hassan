"""Order batching: rider ke ek hi raaste ke 2-3 orders.

Do kaam (sab pure functions, DB ke bina):
1. match_offer  - naya offer rider ke maujooda orders ke saath "ek raaste" ka hai ya nahi.
2. plan_route   - rider ke active orders ka suggested sequence (pehle sab store se maal, phir
                  customers - sab se qareeb wala pehle) aur Google Maps multi-stop link.
Coordinates na hon to address se kaam chalta hai; kuch bhi na ho to koi badge/plan nahi banta.
"""
from urllib.parse import quote

from .dispatch import haversine_km

NEAR_STORE_KM = 1.5     # dono stores itne qareeb = saath uthaya ja sakta hai
NEAR_DROP_KM = 2.5      # dono customers itne qareeb = ek hi raaste par
MAX_WAYPOINTS = 8       # Google Maps URL ki hadd (9) se kam


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _dist(a, b):
    """(lat, lng) ya None ke darmiyan km; coordinates na hon to None."""
    if not a or not b or None in a or None in b:
        return None
    return haversine_km(a[0], a[1], b[0], b[1])


def match_offer(offer, actives):
    """offer: {'vendor_id','store_ll','drop_ll'}; actives: isi shakal ki list.
    Return: 'same_store' | 'near_store' | 'same_area' | None (sab se majboot match pehle)."""
    if not actives:
        return None
    if offer.get('vendor_id') and any(a.get('vendor_id') == offer['vendor_id'] for a in actives):
        return 'same_store'
    for a in actives:
        d = _dist(offer.get('store_ll'), a.get('store_ll'))
        if d is not None and d <= NEAR_STORE_KM:
            return 'near_store'
    for a in actives:
        d = _dist(offer.get('drop_ll'), a.get('drop_ll'))
        if d is not None and d <= NEAR_DROP_KM:
            return 'same_area'
    return None


def _nearest_first(stops, start):
    """Nearest-neighbour tarteeb. Bina coordinates wale stops aakhir mein, apni asli tarteeb mein."""
    located = [s for s in stops if s['ll']]
    rest = [s for s in stops if not s['ll']]
    out, cur = [], start
    while located:
        if cur:
            nxt = min(located, key=lambda s: _dist(cur, s['ll']))
        else:
            nxt = located[0]
        located.remove(nxt)
        out.append(nxt)
        cur = nxt['ll']
    return out + rest


BRUTE_MAX_STOPS = 8     # itne stops tak sab tarteebon mein se behtareen dhoondte hain (6 stops = 720 mumkin)


def _matches_lock(stop, lock):
    """lock = 'p:<order_id>' ya 'd:<order_id>' - rider ka maujooda stop (route baar baar na ulte)."""
    try:
        kind, oid = str(lock).split(':', 1)
        return stop['kind'][0] == kind and int(oid) in stop['order_ids']
    except (ValueError, TypeError, KeyError):
        return False


def _sequence(stops, start, lock_first=None):
    """Stops ki behtareen tarteeb. Har stop {'id','ll','after'} - 'after' = pehle ye stop poora ho (pickup -> drop).

    <= BRUTE_MAX_STOPS: poori talash (sab se kam kul doori). Zyada: nearest-neighbour (precedence ka khayal rakh kar)."""
    n = len(stops)

    def can_go(s, done):
        return s['after'] is None or s['after'] in done

    def step_cost(cur, s):
        return _dist(cur, s['ll']) or 0.0 if cur and s['ll'] else 0.0

    forced = None
    if lock_first:
        forced = next((s for s in stops if _matches_lock(s, lock_first) and can_go(s, set())), None)

    if n > BRUTE_MAX_STOPS:
        out, done, cur = [], set(), start
        pool = list(stops)
        if forced:
            pool.remove(forced)
            out.append(forced); done.add(forced['id']); cur = forced['ll'] or cur
        while pool:
            ok = [s for s in pool if can_go(s, done)] or pool
            nxt = min(ok, key=lambda s: step_cost(cur, s))
            pool.remove(nxt)
            out.append(nxt); done.add(nxt['id']); cur = nxt['ll'] or cur
        return out

    best = {'cost': None, 'seq': None}

    def rec(seq, done, cur, cost):
        if best['cost'] is not None and cost >= best['cost']:
            return
        if len(seq) == n:
            best['cost'], best['seq'] = cost, list(seq)
            return
        for s in stops:
            if s['id'] in done or not can_go(s, done):
                continue
            if forced and not seq and s is not forced:
                continue
            seq.append(s); done.add(s['id'])
            rec(seq, done, s['ll'] or cur, cost + step_cost(cur, s))
            seq.pop(); done.discard(s['id'])

    rec([], set(), start, 0.0)
    return best['seq'] or list(stops)


def plan_route(orders, start=None, lock_first=None, min_orders=2):
    """orders: [{'order_no','order_id'(optional),'status','vendor_id','store_name','store_ll','store_addr',
                 'cust_name','drop_ll','cust_addr'}]
    status 'assigned' = maal abhi store se uthana hai. start = rider ki (lat, lng) ya None.
    Return {'stops': [...], 'google': url|'' } ; min_orders se kam orders par None.

    Tarteeb: har customer ka drop uske pickup ke BAAD; baqi sab tarteeb mein sab se kam kul doori
    (pehle ki tarah 'pehle sab pickups phir sab drops' zaroori nahi - agar pickup-drop-pickup-drop kam doori ho to wahi).
    Bina coordinates wale pickups sab se pehle, bina coordinates wale drops sab se aakhir mein.
    lock_first: rider jis stop par ja raha hai use pehle hi rakho (har refresh par tarteeb na ulte)."""
    if len(orders) < min_orders:
        return None

    pickups, seen, pick_of = [], {}, {}
    for o in orders:
        oid = o.get('order_id', o['order_no'])
        if o['status'] != 'assigned':
            continue
        key = o.get('vendor_id') or ('addr', o.get('store_addr'))
        if key in seen:
            seen[key]['orders'].append(o['order_no'])
            seen[key]['order_ids'].append(oid)
            pick_of[oid] = seen[key]
            continue
        s = {'kind': 'pickup', 'label': o.get('store_name') or 'Store', 'll': o.get('store_ll'),
             'addr': o.get('store_addr') or '', 'orders': [o['order_no']], 'order_ids': [oid],
             'id': f'p{len(pickups)}', 'after': None}
        seen[key] = s
        pick_of[oid] = s
        pickups.append(s)

    drops = []
    for i, o in enumerate(orders):
        oid = o.get('order_id', o['order_no'])
        drops.append({'kind': 'drop', 'label': o.get('cust_name') or 'Customer', 'll': o.get('drop_ll'),
                      'addr': o.get('cust_addr') or '', 'orders': [o['order_no']], 'order_ids': [oid],
                      'id': f'd{i}', 'after': pick_of[oid]['id'] if oid in pick_of else None})

    head = [s for s in pickups if not s['ll']]            # location nahi: sab se pehle
    tail = [s for s in drops if not s['ll']]              # location nahi: sab se aakhir
    mid = [s for s in pickups + drops if s['ll']]
    head_ids = {s['id'] for s in head}
    for s in mid:                                         # head wale pickup pehle hi ho chuke maane jayen
        if s['after'] in head_ids:
            s['after'] = None
    ordered = head + _sequence(mid, start, lock_first) + tail

    stops = [s for s in ordered if s['ll'] or s['addr']]
    if len(stops) < 2 and min_orders > 1:
        return None
    if not stops:
        return None
    for i, s in enumerate(stops, 1):
        s['n'] = i
        s['key'] = f'{s["kind"][0]}:{s["order_ids"][0]}'
        s.pop('after', None)
    return {'stops': stops, 'google': _google_url(stops)}


def _point(s):
    return f'{s["ll"][0]},{s["ll"][1]}' if s['ll'] else s['addr']


def _google_url(stops):
    """Pehla stop-ke-ilawa sab 'waypoints'; aakhri stop 'destination'. Bohat stops ho to pehle MAX_WAYPOINTS tak."""
    stops = stops[:MAX_WAYPOINTS + 1]
    dest = _point(stops[-1])
    way = '|'.join(_point(s) for s in stops[:-1])
    url = f'https://www.google.com/maps/dir/?api=1&destination={quote(dest)}&travelmode=two-wheeler'
    if way:
        url += f'&waypoints={quote(way)}'
    return url
