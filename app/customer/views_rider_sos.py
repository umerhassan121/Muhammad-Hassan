"""Rider SOS: rider ka button aur admin ka alert page."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import RiderSOS
from ..shop_flags import shop_flag
from . import rider_sos
from .views_rider_portal import _admin_only, rider_login_required


@rider_login_required
@require_POST
def rider_sos_send(request):
    if not shop_flag('rider_sos_enabled'):
        messages.error(request, 'SOS is currently unavailable. Call %s if you are in danger.' % rider_sos.EMERGENCY_NUMBER)
        return redirect(request.META.get('HTTP_REFERER') or 'rider_home')
    rider = request.user.rider_profile
    alert, created = rider_sos.trigger(rider, request.POST.get('lat'), request.POST.get('lng'), request.POST.get('note'))
    if created:
        messages.warning(request, '🆘 SOS sent. The admin has been alerted. If you are in danger, call %s now.'
                         % rider_sos.EMERGENCY_NUMBER)
    else:
        messages.warning(request, '🆘 Your SOS is already open - the admin was alerted. Call %s if you need help now.'
                         % rider_sos.EMERGENCY_NUMBER)
    return redirect('rider_home')


@_admin_only
def rider_sos_admin(request):
    if request.method == 'POST':
        alert = get_object_or_404(RiderSOS, pk=request.POST.get('sos_id') or 0)
        rider_sos.resolve(alert, request.user, request.POST.get('admin_note'))
        messages.success(request, f'✅ SOS of {alert.rider.name} closed.')
        return redirect('rider_sos_admin')
    open_qs = list(RiderSOS.objects.filter(status='open').select_related('rider', 'delivery__sale_order'))
    for a in open_qs:
        a.map = rider_sos.map_url(a)
    recent = RiderSOS.objects.filter(status='resolved').select_related('rider', 'resolved_by')[:20]
    return render(request, 'customer_portal/rider/sos_admin.html', {'open_alerts': open_qs, 'recent': recent})
