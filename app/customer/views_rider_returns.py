"""Failed delivery: customer ka "I am ready" button aur admin ka faisla (re-dispatch / cancel)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import DeliveryFailure, SaleOrder
from . import delivery_returns
from .delivery_returns import ReturnError
from .views_rider_portal import _admin_only


@customer_login_required
@require_POST
def customer_ready_for_rider(request, order_id):
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Access denied')
        return redirect('shop_home')
    customer = request.user.customer_profile.customer
    order = get_object_or_404(SaleOrder, id=order_id, customer=customer)
    try:
        delivery_returns.customer_ready(order, customer)
        messages.success(request, '🙋 Thanks! We told your rider you are ready.')
    except ReturnError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('order_detail_customer', order_id=order.id)


@_admin_only
def rider_returns_admin(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            fid = int(request.POST.get('failure_id') or 0)
            if action == 'redispatch':
                f = delivery_returns.redispatch(fid, request.user)
                messages.success(request, f'🔁 Order #{f.sale_order.order_no} is back in the rider offers.')
            elif action == 'cancel':
                f = delivery_returns.cancel_order(fid, request.user, request.POST.get('reason'))
                messages.success(request, f'❌ Order #{f.sale_order.order_no} cancelled.')
            else:
                messages.error(request, '❌ Invalid action.')
        except (ReturnError, ValueError, DeliveryFailure.DoesNotExist) as exc:
            messages.error(request, f'❌ {exc}')
        return redirect('rider_returns_admin')
    waiting = (DeliveryFailure.objects.filter(status='waiting')
               .select_related('sale_order', 'sale_order__vendor', 'sale_order__customer', 'rider'))
    returned = (DeliveryFailure.objects.filter(status='returned')
                .select_related('sale_order', 'sale_order__vendor', 'sale_order__customer', 'rider'))
    recent = (DeliveryFailure.objects.filter(status='closed')
              .select_related('sale_order', 'rider').order_by('-closed_at')[:20])
    return render(request, 'customer_portal/rider/returns_admin.html',
                  {'waiting': waiting, 'returned': returned, 'recent': recent})
