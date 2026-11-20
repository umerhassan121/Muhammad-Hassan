"""Customer side: ⚡ Mart home (Talabat Mart jaisa grocery experience).

- mart_home          : /shop/mart/   (dark store ke aisles: Deals, har category ki row, search, cart bar)
- mart_substitution  : /shop/mart/substitution/  (POST: out-of-stock par kya karein)

Sirf approved dark stores (VendorProfile.is_dark_store) aur unke live products. Aisle ka "See all"
?category= se us category ke saare products (24 per page) dikhata hai.
"""
import json
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import VendorProfile
from . import delivery_pricing, substitution
from .views_customer_portal import get_cart_count_value, get_delivery_area, get_product_final_price
from .views_stores import CURRENCY, STATUS_ORDER, _company_name, _live_products, store_serves_area
from .voice_terms import q_any

AISLE_PREVIEW = 8      # home par har category ke kitne items
PAGE_SIZE = 24


def _mart_stores():
    return list(VendorProfile.objects.filter(
        is_approved=True, is_dark_store=True, vendor__in=_live_products().values('vendor'),
    ).select_related('vendor', 'store_category'))


def _pick_store(stores, request, area):
    """?store= wala, warna khula + customer ke area mein wala pehle."""
    try:
        wanted = int(request.GET.get('store', ''))
    except (TypeError, ValueError):
        wanted = None
    for s in stores:
        if wanted and s.pk == wanted:
            return s
    ranked = sorted(stores, key=lambda s: (
        0 if store_serves_area(s.city, area, s.delivery_areas) else 1,
        STATUS_ORDER.get(s.status_label, 2), s.business_name.lower()))
    return ranked[0] if ranked else None


def _stocked(qs):
    return qs.annotate(total_stock=Coalesce(
        Sum('inventory__stock'), Value(0.0), output_field=DecimalField(max_digits=20, decimal_places=2)))


def _decorate(products, cart_state):
    from ..models import ProductOptionGroup
    from .deals import store_view as deals_store_view
    from .item_schedule import annotate as annotate_schedule
    products = list(products)
    if not products:
        return products
    option_pids = set(ProductOptionGroup.objects.filter(
        product__in=products, is_active=True).values_list('product_id', flat=True))
    annotate_schedule(products)
    badges, _deals = deals_store_view(products[0].vendor_id)
    for p in products:
        p.has_options = p.id in option_pids
        p.final_price = get_product_final_price(p)
        p.has_discount = bool(p.discount_percentage and p.discount_percentage > 0)
        p.old_price = None
        if p.has_discount and p.discount_percentage < 100:
            try:
                p.old_price = (Decimal(p.final_price) / (Decimal(1) - Decimal(p.discount_percentage) / Decimal(100))
                               ).quantize(Decimal('0.001'))
            except Exception:
                p.old_price = None
        p.cart_qty = cart_state.get(str(p.id), {}).get('qty', 0)
        p.stock_int = int(p.total_stock or 0)
        p.deal_badge = badges.get(p.id)
    return products


def mart_home(request):
    area = get_delivery_area(request)
    stores = _mart_stores()
    store = _pick_store(stores, request, area)
    base_ctx = {'currency': CURRENCY, 'company_name': _company_name(),
                'cart_count': get_cart_count_value(request)}
    if store is None:
        return render(request, 'customer_portal/mart.html', {**base_ctx, 'store': None})

    base = _live_products().filter(vendor=store.vendor)
    if store.hide_sold_out:
        from .stock_alerts import hide_sold_out
        base = hide_sold_out(base)

    search = request.GET.get('q', '').strip()[:100]
    try:
        category_id = int(request.GET.get('category', ''))
    except (TypeError, ValueError):
        category_id = None

    aisles = list(base.exclude(category__isnull=True).values('category_id', 'category__name')
                  .annotate(n=Count('id')).order_by('category__name'))
    cart = request.session.get('cart', {})
    cart_state = {}
    for key, item in cart.items():
        if (item.get('vendor_id') or 0) == store.vendor_id:
            cart_state[str(key)] = {'qty': int(item.get('quantity', 0) or 0), 'price': float(item.get('price', 0) or 0)}

    mode, sections, page_obj, title = 'home', [], None, ''
    if search or category_id:
        mode = 'list'
        qs = _stocked(base.select_related('category', 'unit'))
        if category_id:
            qs = qs.filter(category_id=category_id)
            title = next((a['category__name'] for a in aisles if a['category_id'] == category_id), '')
        if search:
            qs = qs.filter(q_any(['name', 'description'], search))
            title = f'Results for "{search}"'
        page_obj = Paginator(qs.order_by('name'), PAGE_SIZE).get_page(request.GET.get('page', 1))
        _decorate(page_obj.object_list, cart_state)
    else:
        deals = list(_stocked(base.filter(discount_percentage__gt=0).select_related('category', 'unit'))
                     .order_by('-discount_percentage', 'name')[:AISLE_PREVIEW])
        if deals:
            sections.append({'title': '🔥 Deals', 'category_id': None, 'items': _decorate(deals, cart_state)})
        popular = list(_stocked(base.filter(is_popular=True).select_related('category', 'unit'))
                       .order_by('name')[:AISLE_PREVIEW])
        if popular:
            sections.append({'title': '⭐ Popular', 'category_id': None, 'items': _decorate(popular, cart_state)})
        for a in aisles:
            items = list(_stocked(base.filter(category_id=a['category_id']).select_related('category', 'unit'))
                         .order_by('name')[:AISLE_PREVIEW])
            sections.append({'title': a['category__name'], 'category_id': a['category_id'],
                             'count': a['n'], 'items': _decorate(items, cart_state)})

    for i, sec in enumerate(sections):
        sec['idp'] = f'm{i}'          # har section ke card ids alag (page par dohraye hue maal ke liye)
    fee = delivery_pricing.quote(store, request)
    return render(request, 'customer_portal/mart.html', {
        **base_ctx,
        'store': store, 'status': store.status_label, 'other_marts': [s for s in stores if s.pk != store.pk],
        'in_area': store_serves_area(store.city, area, store.delivery_areas), 'delivery_area': area,
        'aisles': aisles, 'sections': sections, 'mode': mode, 'products': page_obj, 'page_obj': page_obj,
        'list_title': title, 'search': search, 'selected_category': category_id,
        'fee_now': fee['fee'], 'fee_too_far': fee['out_of_range'], 'fee_range_message': fee['message'],
        'cart_state': cart_state, 'cart_other': bool(cart) and not cart_state,
    })


@require_POST
def mart_substitution(request):
    try:
        data = json.loads(request.body) if request.body else request.POST
    except ValueError:
        data = request.POST
    pref = substitution.clean(data.get('pref'))
    request.session[substitution.SESSION_KEY] = pref
    request.session.modified = True
    return JsonResponse({'success': True, 'pref': pref})
