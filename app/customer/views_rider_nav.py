"""Rider in-app navigation: single order + BATCH (multi-stop) navigation. Sirf rider ke apne active orders ke liye.

  shop/rider/navigate/<order>/            ek order ka map (store ya customer tak)
  shop/rider/navigate/<order>/route/      us ka route (JSON)
  shop/rider/navigate/batch/              sab active orders ek raaste mein (Talabat jaisa multi-stop)
  shop/rider/navigate/batch/route/        poora multi-stop route + stops (JSON)
  shop/rider/navigate/batch/pickup/       ek store ke saare orders "Picked up" (ek tap)
"""
from django.contrib import messages
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import DeliveryInfo
from ..shop_flags import flag_required
from . import batch_nav, rider_nav
from .views_rider_portal import ACTIVE_STATUSES, _nav_links, _rider_ctx, rider_login_required

BATCH_MIN_FETCH_GAP_SECONDS = 3


def _lang(request):
    """Awaaz / banner ki zuban: 'ar' ya 'en' (portal ki zuban Urdu ho to bhi navigation English)."""
    code = request.GET.get('lang')
    if code not in ('ar', 'en'):
        try:
            from app.i18n.i18n_lang import get_language
            code = get_language(request).get('code')
        except Exception:
            code = 'en'
    return 'ar' if code == 'ar' else 'en'


def _map_cfg():
    """Map tiles / currency (settings se badal sakte hain: RIDER_NAV_TILE_URL, RIDER_NAV_TILE_ATTR, RIDER_NAV_CURRENCY).

    Default OpenStreetMap hai (sirf chhote use ke liye); production mein apna tile provider lagayen."""
    from django.conf import settings
    out = {'currency': getattr(settings, 'RIDER_NAV_CURRENCY', 'Rs.')}
    tile = getattr(settings, 'RIDER_NAV_TILE_URL', '')
    if tile:
        out['tile'] = tile
        out['tile_attr'] = getattr(settings, 'RIDER_NAV_TILE_ATTR', '')
    return out


def _my_delivery(request, order_id):
    """Rider ka apna active delivery (dusre rider ka order nahi khulta)."""
    return get_object_or_404(
        DeliveryInfo.objects.select_related('sale_order__customer', 'sale_order__vendor'),
        sale_order_id=order_id, rider=request.user.rider_profile, status__in=ACTIVE_STATUSES)


def _rider_point(rider):
    from . import dispatch
    from django.utils import timezone
    return dispatch._rider_coords(rider, timezone.now())


@rider_login_required
@flag_required('rider_inapp_nav_enabled', redirect_to='rider_home')
def rider_navigate(request, pk):
    from django.urls import reverse
    di = _my_delivery(request, pk)
    dest = rider_nav.leg_dest(di)
    has_point = dest['lat'] is not None and dest['lng'] is not None
    lang = _lang(request)
    cfg = {
        'mode': 'single', 'lang': lang,
        'route_url': reverse('rider_nav_route', args=[pk]),
        'dest': [dest['lat'], dest['lng']] if has_point else None,
        'dest_name': dest['name'], 'leg': dest['leg'],
        'back_url': reverse('rider_home'),
        'order_no': di.sale_order.order_no, 'has_map': has_point,
        'ext': _nav_links(dest['lat'], dest['lng'], dest['addr']), **_map_cfg(),
    }
    return render(request, 'customer_portal/rider/navigate.html', _rider_ctx(
        request, 'orders', order=di.sale_order, dest=dest, has_point=has_point, has_map=has_point, cfg=cfg))


@rider_login_required
@flag_required('rider_inapp_nav_enabled', json=True)
def rider_nav_route(request, pk):
    """GET ?lat=&lng= (rider ki position) -> route us ki maujooda manzil tak."""
    rider = request.user.rider_profile
    di = _my_delivery(request, pk)
    # ek rider se bohat tezi se requests na aayen (routing service ka rate limit)
    if not cache.add(f'rider_nav_rl:{rider.pk}', 1, rider_nav.MIN_FETCH_GAP_SECONDS):
        return JsonResponse({'success': False, 'message': 'Please wait a few seconds.'}, status=429)
    dest = rider_nav.leg_dest(di)
    if dest['lat'] is None or dest['lng'] is None:
        return JsonResponse({'success': False, 'message': 'This destination has no map location. Use Google Maps.'},
                            status=404)
    try:
        frm = rider_nav.valid_point(request.GET.get('lat'), request.GET.get('lng'))
    except rider_nav.NavError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    try:
        route = rider_nav.fetch_route(frm, (dest['lat'], dest['lng']), lang=_lang(request))
    except rider_nav.NavError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=502)
    return JsonResponse({'success': True, 'leg': dest['leg'], **route})


# ============================================
# BATCH NAVIGATION
# ============================================

@rider_login_required
@flag_required('rider_batch_nav_enabled', redirect_to='rider_home')
def rider_batch_navigate(request):
    """Rider ke sab active orders ek multi-stop map par."""
    from django.urls import reverse
    rider = request.user.rider_profile
    data = batch_nav.build(rider, start=_rider_point(rider), lock=request.GET.get('cur'))
    if not data['infos']:
        messages.info(request, 'ℹ️ You have no active orders to navigate.')
        return redirect('rider_home')
    if len(data['infos']) == 1:      # ek hi order: seedha single navigation
        return redirect('rider_navigate', pk=data['infos'][0]['order_id'])
    stops = batch_nav.public_stops(data['plan'], data['infos']) if data['plan'] else []
    if not stops:
        messages.info(request, 'ℹ️ These orders have no map location. Use the Google Maps buttons.')
        return redirect('rider_home')
    cfg = {
        'mode': 'batch', 'lang': _lang(request),
        'route_url': reverse('rider_batch_route'),
        'pickup_url': reverse('rider_batch_pickup'),
        'home_url': reverse('rider_home'), 'back_url': reverse('rider_home'),
        'order_url': reverse('rider_home'),
        'stops': stops,
        'google': data['plan']['google'] if data['plan'] else '', 'has_map': True, **_map_cfg(),
    }
    return render(request, 'customer_portal/rider/batch_navigate.html', _rider_ctx(
        request, 'orders', cfg=cfg, stop_count=len(stops), order_count=len(data['infos'])))


@rider_login_required
@flag_required('rider_batch_nav_enabled', json=True)
def rider_batch_route(request):
    """GET ?lat=&lng=&cur=<stop key> -> baqi stops ka tarteeb-wala poora route.

    Har baar DB se hisaab: jo pickup / delivery ho chuki wo stops khud hat jate hain."""
    rider = request.user.rider_profile
    if not cache.add(f'rider_nav_rl:b:{rider.pk}', 1, BATCH_MIN_FETCH_GAP_SECONDS):
        return JsonResponse({'success': False, 'message': 'Please wait a few seconds.'}, status=429)
    try:
        frm = rider_nav.valid_point(request.GET.get('lat'), request.GET.get('lng'))
    except rider_nav.NavError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)

    data = batch_nav.build(rider, start=frm, lock=request.GET.get('cur'))
    if not data['infos'] or not data['plan']:
        return JsonResponse({'success': True, 'done': True, 'stops': []})
    stops = batch_nav.public_stops(data['plan'], data['infos'])
    located = [s for s in stops if s['ll']]
    if not located:
        return JsonResponse({'success': False, 'stops': stops,
                             'message': 'None of the stops has a map location. Use Google Maps.'}, status=404)
    try:
        route = rider_nav.fetch_multi([frm] + [tuple(s['ll']) for s in located], lang=_lang(request))
    except rider_nav.NavError as exc:
        return JsonResponse({'success': False, 'stops': stops, 'message': str(exc)}, status=502)
    batch_nav.annotate(located, route['legs'])
    return JsonResponse({'success': True, 'done': False, 'stops': stops,
                         'google': data['plan']['google'], **route})


@rider_login_required
@flag_required('rider_batch_nav_enabled', json=True)
@require_POST
def rider_batch_pickup(request):
    """POST order_ids=1&order_ids=2 -> ek store ke orders ek tap mein 'Picked up'.

    Asal kaam rider_order_action(pickup) karta hai (wohi checks, tracking, customer notification)."""
    from . import views_rider_portal
    rider = request.user.rider_profile
    ids = []
    for raw in request.POST.getlist('order_ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids or len(ids) > 10:
        return JsonResponse({'success': False, 'message': 'No orders selected.'}, status=400)
    mine = set(DeliveryInfo.objects.filter(rider=rider, sale_order_id__in=ids, status='assigned')
               .values_list('sale_order_id', flat=True))
    if not mine:
        return JsonResponse({'success': False, 'message': 'These orders are already picked up.'}, status=409)
    for oid in ids:
        if oid in mine:
            views_rider_portal.rider_order_action(request, oid, 'pickup')
    still = set(DeliveryInfo.objects.filter(rider=rider, sale_order_id__in=mine, status='assigned')
                .values_list('sale_order_id', flat=True))
    if still:
        from ..shop_flags import shop_flag
        msg = ('The store pickup code is on. Open each order and enter its 4-digit code from the store.'
               if shop_flag('rider_pickup_code_required') else
               'Pickup could not be confirmed. Open the order and try again.')
        return JsonResponse({'success': False, 'message': msg,
                             'pending': sorted(still)}, status=409)
    cache.delete(f'rider_nav_rl:b:{rider.pk}')      # agla route foran mil jaye
    return JsonResponse({'success': True, 'picked': sorted(mine)})
