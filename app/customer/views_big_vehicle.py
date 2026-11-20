"""Bari gari (bhaari order): store online gari list se chunta hai ya manually likhta hai, kiraya likhta hai, customer manzoor ya radd karta hai.

Flow: store order accept kare -> goods adda se kiraya pooch kar yahan bheje -> customer order page par
manzoor kare -> delivery fee yehi kiraya ban jati hai -> order bike riders ko nahi dikhta -> store
"Ready" aur "Delivered" khud karta hai.
"""
import logging
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required, vendor_login_required
from ..models import SaleOrder
from ..shop_flags import flag_required
from . import store_orders
from .vendor_access import get_vendor_profile
from .views_favorites import current_customer

logger = logging.getLogger(__name__)


@vendor_login_required
@flag_required('vendor_can_manage_orders')
@require_POST
def vendor_big_vehicle(request, pk):
    prof = get_vendor_profile(request.user)
    back = redirect(f"{reverse('vendor_orders')}?tab=active")
    if not prof.is_approved:
        messages.error(request, '❌ You can handle orders only after your account is approved.')
        return back
    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk, vendor=prof.vendor)
            if request.POST.get('intent') == 'rider':
                store_orders.withdraw_big_vehicle(order)
                messages.success(request, f'🏍️ Order #{order.order_no}: the vehicle fare was withdrawn. You can now mark it Ready and a rider will take it.')
            elif request.POST.get('intent') == 'driver':
                store_orders.assign_big_vehicle_driver(order, request.POST.get('driver_id'))
                messages.success(request, f'🚚 Order #{order.order_no}: vehicle updated.')
            elif request.POST.get('intent') == 'details':
                store_orders.update_big_vehicle_details(
                    order, vehicle_no=request.POST.get('vehicle_no', ''),
                    driver_phone=request.POST.get('driver_phone', ''))
                messages.success(request, f'✅ Order #{order.order_no}: vehicle details saved.')
            else:
                store_orders.propose_big_vehicle(
                    order, vtype=request.POST.get('vehicle_type', ''),
                    fee=request.POST.get('fee', ''), note=request.POST.get('note', ''),
                    user=request.user, driver_id=request.POST.get('driver_id'))
                picked = f' (vehicle: {order.big_vehicle_driver.name})' if order.big_vehicle_driver_id else ''
                messages.success(request, f'🚚 Order #{order.order_no}: fare sent to the customer{picked}. Waiting for their approval.')
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
    except Exception as exc:
        logger.error('Big vehicle (vendor) error: %s', exc)
        messages.error(request, '❌ Could not save the fare. Please try again.')
    return back


@customer_login_required
@require_POST
def big_vehicle_respond(request, order_id):
    customer = current_customer(request)
    if customer is None:
        return redirect('my_account')
    approve = request.POST.get('choice') == 'approve'
    # Waqt khatam ho chuka ho to pehle order cancel karo, phir jawab qabool na karo
    try:
        if store_orders.expire_big_vehicle_proposals(order_id=order_id):
            messages.info(request, '⏰ The time to respond has passed, so the order was cancelled.')
            return redirect('order_detail_customer', order_id=order_id)
    except Exception as exc:
        logger.error('Big vehicle (expire on respond) error: %s', exc)
    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(),
                                      pk=order_id, customer=customer, vendor__isnull=False)
            store_orders.respond_big_vehicle(order, approve=approve)
        if approve:
            total = store_orders.order_payable_total(order)
            due = store_orders.order_cash_due(order)
            extra = (f' Cash on delivery: Rs. {due:,.0f}.' if (order.payment_method or 'cod') == 'cod' else '')
            messages.success(request, f'✅ Fare approved. New total Rs. {total:,.0f}.{extra}')
        else:
            messages.info(request, 'The order has been cancelled.')
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
    except Exception as exc:
        logger.error('Big vehicle (customer) error: %s', exc)
        messages.error(request, '❌ Could not save your response. Please try again.')
    return redirect('order_detail_customer', order_id=order_id)


def _rider_job_response(request, pk, fn, ok_msg):
    rider = request.user.rider_profile
    if rider.rider_kind != 'big_vehicle':
        messages.error(request, '❌ This is only for big vehicle drivers.')
        return redirect('rider_home')
    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk, big_vehicle_driver=rider)
            fn(order, rider)
        messages.success(request, ok_msg(order))
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
    except Exception as exc:
        logger.error('Big vehicle (driver) error: %s', exc)
        messages.error(request, '❌ Could not save. Please try again.')
    return redirect('rider_home')


def rider_big_vehicle_respond(request, pk):
    accept = request.POST.get('choice') == 'accept'
    return _rider_job_response(
        request, pk, lambda o, r: store_orders.driver_respond_big_vehicle(o, r, accept=accept),
        lambda o: f'✅ Job #{o.order_no} accepted.' if accept else f'Job #{o.order_no} declined.')


def rider_big_vehicle_delivered(request, pk):
    return _rider_job_response(
        request, pk, store_orders.driver_deliver_big_vehicle,
        lambda o: f'🎉 Order #{o.order_no} marked as delivered.')
