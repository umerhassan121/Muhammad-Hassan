"""Vendor portal: Item schedule (kuch ghanton / dinon ke liye hi item available).

- vendor_item_schedule : /shop/vendor/schedule/   har approved item ka waqt + din; save / clear
Schedule ke bahar item customer ko nazar aata hai magar order nahi hota. Review dobara nahi chahiye.
"""
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import vendor_login_required
from ..models import Product
from ..shop_flags import flag_required
from . import item_schedule as sched
from .vendor_access import get_vendor_profile

logger = logging.getLogger(__name__)


def _company_name():
    from ..models import CompanyInfo
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


@vendor_login_required
@flag_required('vendor_can_add_products', redirect_to='vendor_dashboard')
def vendor_item_schedule(request):
    profile = get_vendor_profile(request.user)
    vendor = profile.vendor
    if request.method == 'POST':
        product = get_object_or_404(Product, pk=request.POST.get('product_id') or 0, vendor=vendor)
        try:
            if request.POST.get('action') == 'clear':
                sched.save_schedule(product, None, None, [])
                messages.success(request, f'✅ "{product.name}" ka schedule hata diya (ab poora din available).')
            else:
                result = sched.save_schedule(
                    product, sched.parse_time(request.POST.get('avail_from')),
                    sched.parse_time(request.POST.get('avail_to')), request.POST.getlist('days'))
                messages.success(request, f'✅ Schedule saved for "{product.name}".' if result == 'saved'
                                 else f'✅ "{product.name}": no schedule, available all day.')
        except ValueError as exc:
            messages.error(request, f'❌ {product.name}: {exc}')
        except Exception:
            logger.exception('item schedule save failed (product=%s)', product.pk)
            messages.error(request, '❌ Something went wrong. Please try again.')
        return redirect('vendor_item_schedule')

    now = timezone.localtime()
    rows = []
    for p in (Product.objects.filter(vendor=vendor, approval_status='approved')
              .select_related('category', 'schedule').order_by('category__name', 'name')):
        s = getattr(p, 'schedule', None)
        rows.append({
            'p': p, 's': s,
            'days': sched.parse_days(s.days) if s else set(),
            'text': sched.describe(s) if s else '',
            'off_now': bool(s) and not sched.is_available_at(s, now),
        })
    return render(request, 'customer_portal/vendor/item_schedule.html', {
        'page_title': 'Item schedule', 'rows': rows, 'profile': profile,
        'day_names': list(enumerate(sched.DAY_NAMES)), 'company_name': _company_name(),
        'scheduled_n': sum(1 for r in rows if r['s']),
    })
