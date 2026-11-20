"""Rider ki payout request: bhejna aur cancel karna (admin ka Paid/Reject rider_detail page par hai)."""
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..shop_flags import flag_required
from . import rider_payouts
from .rider_payouts import PayoutError
from .views_rider_portal import rider_login_required


@rider_login_required
@flag_required('rider_payout_request_enabled', redirect_to='rider_earnings')
@require_POST
def rider_payout_request(request):
    rider = request.user.rider_profile
    try:
        req = rider_payouts.create_request(
            rider, request.POST.get('amount'), request.POST.get('method'),
            request.POST.get('account_title'), request.POST.get('account_no'), request.POST.get('note'))
        messages.success(request, f'✅ Request for Rs. {req.amount:,.0f} sent. You will be notified when it is paid.')
    except PayoutError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('rider_earnings')


@rider_login_required
@require_POST
def rider_payout_cancel(request, pk):
    try:
        rider_payouts.cancel_request(request.user.rider_profile, pk)
        messages.success(request, 'Request cancelled.')
    except PayoutError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('rider_earnings')
