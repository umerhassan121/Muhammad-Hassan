"""Vendor portal: Receipt print + POS / printer integration.

Portal pages (login zaroori, CSRF laga hua):
- vendor_order_receipt : /shop/vendor/orders/<id>/receipt/   thermal receipt (58 / 80 mm), ?w=58  ?auto=1 (khud print dialog)
- vendor_pos           : /shop/vendor/pos/                   API token banao / band karo (sirf owner), API ki madad

POS API (token se, cookies istemal nahi hote - is liye CSRF ki zaroorat nahi; dekhein pos_api.py):
- GET  /shop/vendor/pos-api/orders/?status=new|active|done&since_id=N
- POST /shop/vendor/pos-api/orders/<id>/<accept|reject|ready|delivered>/   (JSON ya form: prep_minutes, reason_code, reason_note)
- GET  /shop/vendor/pos-api/menu/
- POST /shop/vendor/pos-api/menu/<product_id>/availability/    {"available": true|false}
"""
import base64
import json
import logging
from functools import wraps

from django.contrib import messages
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from ..decorators import vendor_login_required
from ..models import DeliveryInfo, Product, SaleOrder
from ..shop_flags import flag_required, shop_flag
from . import escpos, pos_api, store_orders
from .vendor_access import get_vendor_profile

logger = logging.getLogger(__name__)

STATUS_GROUPS = {
    'new': ('pending',),
    'active': ('confirmed', 'processing', 'ready'),
    'done': ('delivered', 'cancelled', 'returned'),
}


def _company():
    from ..models import CompanyInfo
    return CompanyInfo.objects.first()


# ============================================================
# 1. RECEIPT PRINT
# ============================================================
@vendor_login_required
@require_GET
def vendor_order_receipt(request, pk):
    profile = get_vendor_profile(request.user)
    # sirf apne store ka order (kisi aur ka -> 404)
    order = get_object_or_404(SaleOrder.objects.select_related('customer'), pk=pk, vendor=profile.vendor)
    items = list(order.items.select_related('product'))
    delivery = DeliveryInfo.objects.filter(sale_order=order).first()
    payload = pos_api.order_payload(order, items, delivery)   # privacy ki shartein ek hi jagah (phone/address)
    width = 58 if request.GET.get('w') == '58' else 80
    company = _company()
    return render(request, 'customer_portal/vendor/order_receipt.html', {
        'profile': profile,
        'order': order,
        'p': payload,
        'items': items,
        'width_mm': width,
        'auto_print': request.GET.get('auto') == '1',
        'is_cod': payload['payment_method'] == 'cod',
        'company_name': company.name if company else '',
        'printed_at': timezone.localtime(),
    })


@vendor_login_required
@require_GET
def vendor_order_escpos(request, pk):
    """Direct printer (Bluetooth / USB) ke liye ESC/POS bytes, base64 mein: {"data": "...", "bytes": N}."""
    profile = get_vendor_profile(request.user)
    order = get_object_or_404(SaleOrder.objects.select_related('customer'), pk=pk, vendor=profile.vendor)
    items = list(order.items.select_related('product'))
    delivery = DeliveryInfo.objects.filter(sale_order=order).first()
    payload = pos_api.order_payload(order, items, delivery)
    width = 58 if request.GET.get('w') == '58' else 80
    company = _company()
    data = escpos.build_receipt(
        payload, profile.business_name, width_mm=width,
        printed_at=timezone.localtime().strftime('%d %b %Y %H:%M'),
        created_text=timezone.localtime(order.order_date).strftime('%d %b %Y, %H:%M') if order.order_date else '',
        company_name=company.name if company else '')
    resp = JsonResponse({'data': base64.b64encode(data).decode('ascii'), 'bytes': len(data)})
    resp['Cache-Control'] = 'no-store'
    return resp


# ============================================================
# 2. TOKEN PAGE (owner)
# ============================================================
@vendor_login_required
def vendor_pos(request):
    profile = get_vendor_profile(request.user)
    new_token = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if not profile.is_approved:
            messages.error(request, '❌ Your account is not approved yet.')
            return redirect('vendor_pos')
        if action == 'create':
            new_token = pos_api.create_token(profile)       # sirf is ek page-load par dikhega
            messages.success(request, '✅ New token created. Copy it now - it is shown only once.')
        elif action == 'revoke':
            pos_api.revoke_token(profile)
            messages.success(request, '✅ Token revoked. Connected devices stop working.')
            return redirect('vendor_pos')
    try:
        rec = profile.pos_token
    except Exception:
        rec = None
    return render(request, 'customer_portal/vendor/pos.html', {
        'profile': profile, 'token_rec': rec, 'new_token': new_token,
        'api_base': request.build_absolute_uri('/shop/vendor/pos-api/'),
    })


# ============================================================
# 3. POS API (token auth)
# ============================================================
def _api(view):
    """Token auth + JSON errors. Session / cookie se kuch nahi liya jata."""
    @csrf_exempt     # cookie auth hai hi nahi: sirf Bearer token (dekhein module docstring)
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        profile = pos_api.profile_for_request(request)
        if profile is None:
            return JsonResponse({'error': 'invalid_or_missing_token'}, status=401)
        if not shop_flag('vendor_can_manage_orders'):
            return JsonResponse({'error': 'order_management_disabled'}, status=403)
        try:
            return view(request, profile, *args, **kwargs)
        except Http404:
            return JsonResponse({'error': 'not_found'}, status=404)
        except store_orders.OrderActionError as exc:
            return JsonResponse({'error': 'action_failed', 'message': str(exc)}, status=409)
        except Exception:
            logger.exception('POS API error')
            return JsonResponse({'error': 'server_error'}, status=500)
    return wrapper


def _body(request):
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            raise store_orders.OrderActionError('Body must be valid JSON.')
    return request.POST


@_api
@require_GET
def pos_orders(request, profile):
    group = request.GET.get('status', 'new')
    if group not in STATUS_GROUPS:
        return JsonResponse({'error': 'bad_status', 'allowed': sorted(STATUS_GROUPS)}, status=400)
    qs = SaleOrder.objects.filter(vendor=profile.vendor, status__in=STATUS_GROUPS[group]).select_related('customer')
    try:
        since = int(request.GET.get('since_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'bad_since_id'}, status=400)
    if since:
        qs = qs.filter(pk__gt=since)
    orders = list(qs.order_by('pk')[:pos_api.FEED_LIMIT])
    out = []
    for o in orders:
        items = list(o.items.select_related('product'))
        delivery = DeliveryInfo.objects.filter(sale_order=o).first()
        out.append(pos_api.order_payload(o, items, delivery))
    return JsonResponse({'orders': out, 'last_id': orders[-1].pk if orders else since})


@_api
@require_POST
def pos_order_action(request, profile, pk, action):
    if action not in ('accept', 'reject', 'ready', 'delivered'):
        raise Http404
    data = _body(request)
    prep = None
    if action == 'accept' and str(data.get('prep_minutes') or '').strip():
        try:
            prep = int(str(data.get('prep_minutes')).strip())
        except ValueError:
            raise store_orders.OrderActionError('prep_minutes must be a whole number.')
        if not 1 <= prep <= 600:
            raise store_orders.OrderActionError('prep_minutes must be between 1 and 600.')
    with transaction.atomic():
        order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk, vendor=profile.vendor)
        store_orders.apply_vendor_action(
            order, action, user=profile.user, prep_minutes=prep,
            reason_code=str(data.get('reason_code') or ''), reason_note=str(data.get('reason_note') or ''))
    return JsonResponse({'ok': True, 'order_no': order.order_no, 'status': order.status})


@_api
@require_GET
def pos_menu(request, profile):
    rows = Product.objects.filter(vendor=profile.vendor, approval_status='approved').order_by('name')
    return JsonResponse({'products': [
        {'id': p.pk, 'name': p.name, 'price': str(p.price),
         'available': bool(p.is_active)} for p in rows[:2000]]})


@_api
@require_POST
def pos_product_availability(request, profile, pk):
    data = _body(request)
    if 'available' not in data:
        return JsonResponse({'error': 'available_required'}, status=400)
    raw = data.get('available')
    available = raw if isinstance(raw, bool) else str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
    product = get_object_or_404(Product, pk=pk, vendor=profile.vendor)
    if product.approval_status != 'approved':
        raise store_orders.OrderActionError('Only an approved product can be shown or hidden.')
    Product.objects.filter(pk=product.pk).update(is_active=available, hidden_by_suspend=False)
    return JsonResponse({'ok': True, 'id': product.pk, 'available': available})
