"""Batch (multi-stop) navigation: rider ke active orders ko ek tarteeb-wale raaste mein badalna.

Server har request par DB se hisaab lagata hai (kaun sa maal uthana baqi hai, kaun sa customer baqi hai),
is liye pickup/delivery ke baad agla stop khud-ba-khud aage aa jata hai - phone par alag se kuch save nahi hota.

  build(rider, start, lock)  -> {'infos': [...], 'plan': {'stops', 'google'} | None}
  public_stops(plan)         -> JSON-safe stops (phone, COD raqam, order numbers ke saath)
  annotate(stops, legs)      -> har stop par pahunchne ka waqt / doori (routing ke legs se)

annotate() / eta_to_order() pure hain (Django ke bina test hote hain); baqi DB use karte hain.
"""
from . import batching

# Har stop par rukne ka andaza (customer ko ETA aur rider ke clock mein jodte hain)
DWELL_PICKUP_S = 180
DWELL_DROP_S = 120


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _ll(lat, lng):
    lat, lng = _f(lat), _f(lng)
    return (lat, lng) if lat is not None and lng is not None else None


def dwell(kind):
    return DWELL_PICKUP_S if kind == 'pickup' else DWELL_DROP_S


# ---------------- DB wala hissa ----------------

def active_deliveries(rider):
    from ..models import DeliveryInfo
    from .views_rider_portal import ACTIVE_STATUSES
    return list(DeliveryInfo.objects
                .filter(rider=rider, status__in=ACTIVE_STATUSES, sale_order__isnull=False)
                .select_related('sale_order', 'sale_order__customer', 'sale_order__vendor')
                .prefetch_related('sale_order__items')
                .order_by('assigned_at', 'id'))


def order_info(di):
    """batching.plan_route ke liye order ki maloomat + stop panel ke liye phone / raqam."""
    from . import dispatch, store_orders
    o = di.sale_order
    cust = o.customer
    s_lat, s_lng = dispatch._store_coords(o)
    vendor = o.vendor if o.vendor_id else None
    phone = getattr(cust, 'contact_number', '') or ''
    is_cod = (o.payment_method or 'cod') == 'cod'
    return {
        'order_id': o.id, 'order_no': o.order_no, 'status': di.status, 'vendor_id': o.vendor_id,
        'store_name': store_orders.store_name(o.vendor_id), 'store_ll': _ll(s_lat, s_lng),
        'store_addr': getattr(vendor, 'address', '') or '',
        'store_phone': getattr(vendor, 'contact_number', '') or '',
        'cust_name': getattr(cust, 'name', '') or '', 'drop_ll': _ll(o.delivery_lat, o.delivery_lng),
        'cust_addr': o.ship_address(), 'cust_phone': phone,
        'items': sum(1 for _ in o.items.all()),
        'is_cod': is_cod, 'cash': float(store_orders.order_cash_due(o)) if is_cod else 0.0,
    }


def build(rider, start=None, lock=None, deliveries=None):
    """Rider ke active orders ka plan. start = rider ki (lat, lng) ya None; lock = maujooda stop ki key."""
    dels = deliveries if deliveries is not None else active_deliveries(rider)
    infos = [order_info(d) for d in dels]
    plan = batching.plan_route(infos, start=start, lock_first=lock, min_orders=1) if infos else None
    return {'infos': infos, 'plan': plan}


def public_stops(plan, infos):
    """Browser ko dene wale stops (sirf wohi maloomat jo rider ko chahiye)."""
    by_id = {i['order_id']: i for i in infos}
    out = []
    for s in plan['stops']:
        rows = [by_id[i] for i in s['order_ids'] if i in by_id]
        first = rows[0] if rows else {}
        digits = ''.join(ch for ch in (first.get('cust_phone') or '') if ch.isdigit())
        is_pick = s['kind'] == 'pickup'
        out.append({
            'n': s['n'], 'key': s['key'], 'kind': s['kind'], 'label': s['label'], 'addr': s['addr'],
            'll': list(s['ll']) if s['ll'] else None,
            'orders': [{'id': r['order_id'], 'no': r['order_no']} for r in rows],
            'phone': (first.get('store_phone') if is_pick else first.get('cust_phone')) or '',
            'wa': '' if is_pick or not digits else f'https://wa.me/{digits}',
            'items': sum(r.get('items', 0) for r in rows),
            'cash': 0.0 if is_pick else sum(r.get('cash', 0.0) for r in rows),
            'cod': (not is_pick) and any(r.get('is_cod') for r in rows),
        })
    return out


# ---------------- pure hissa ----------------

def annotate(stops, legs):
    """stops: wo stops jin ke 'll' hain (rider se shuru ki tarteeb mein); legs: routing ke legs
    [rider->stop1, stop1->stop2, ...] ({'distance_m','duration_s'}).

    Har stop par 'eta_s' (pichhle stops par rukne ka waqt jod kar) aur 'dist_m' (rider se kul doori) lagata hai."""
    t = d = 0.0
    for i, s in enumerate(stops):
        if i < len(legs):
            t += float(legs[i].get('duration_s') or 0)
            d += float(legs[i].get('distance_m') or 0)
        s['eta_s'] = int(round(t))
        s['dist_m'] = int(round(d))
        t += dwell(s['kind'])
    return stops


def stops_before(stops, order_id):
    """(index, kitne stops pehle) is order ke drop stop ka, ya None agar drop stop (location ke saath) nahi."""
    for i, s in enumerate(stops):
        if s['kind'] == 'drop' and order_id in s['order_ids']:
            return i
    return None
