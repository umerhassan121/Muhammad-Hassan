"""Rider support chat: rider ka page + JSON, admin ka inbox + thread + JSON."""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from ..models import RiderProfile, RiderSupportMessage
from ..shop_flags import flag_required
from . import rider_support as sup
from .views_rider_portal import _admin_only, _rider_ctx, rider_login_required

FLAG = 'rider_support_chat_enabled'


def _after(request):
    try:
        return int(request.GET.get('after') or 0)
    except ValueError:
        return 0


def _text(request):
    try:
        if request.content_type == 'application/json':
            return json.loads(request.body or b'{}').get('message')
    except (ValueError, AttributeError):
        return ''
    return request.POST.get('message')


def _messages_json(rider, role, request):
    rows = sup.fetch(rider, _after(request))
    sup.mark_read(rider, role)
    resp = JsonResponse({'success': True, 'messages': [sup.serialize(m, role) for m in rows]})
    resp['Cache-Control'] = 'no-store'
    return resp


def _send_json(rider, role, request):
    try:
        msg = sup.send(rider, role, request.user, _text(request))
    except sup.SupportError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    return JsonResponse({'success': True, 'message': sup.serialize(msg, role)})


# ---------------------------------------------------------------- rider
@rider_login_required
@flag_required(FLAG, redirect_to='rider_home')
def rider_support(request):
    rider = request.user.rider_profile
    sup.mark_read(rider, 'rider')
    return render(request, 'customer_portal/rider/support.html', _rider_ctx(
        request, 'support',
        chat_list_url='/shop/rider/api/support/messages/', chat_send_url='/shop/rider/api/support/send/'))


@require_GET
@rider_login_required
@flag_required(FLAG, json=True)
def rider_support_messages(request):
    return _messages_json(request.user.rider_profile, 'rider', request)


@require_POST
@rider_login_required
@flag_required(FLAG, json=True)
def rider_support_send(request):
    return _send_json(request.user.rider_profile, 'rider', request)


# ---------------------------------------------------------------- admin
@_admin_only
def rider_support_inbox(request):
    rows = []
    for r in RiderProfile.objects.filter(support_messages__isnull=False).distinct():
        last = r.support_messages.order_by('-id').first()
        rows.append({'rider': r, 'last': last,
                     'unread': r.support_messages.filter(sender_role='rider', is_read=False).count()})
    rows.sort(key=lambda x: x['last'].created_at, reverse=True)
    return render(request, 'customer_portal/rider/support_admin.html', {'rows': rows})


@_admin_only
def rider_support_thread(request, pk):
    rider = get_object_or_404(RiderProfile, pk=pk)
    sup.mark_read(rider, 'admin')
    return render(request, 'customer_portal/rider/support_thread.html', {
        'r': rider, 'chat_list_url': f'/shop/rider/manage/support/{rider.pk}/messages/',
        'chat_send_url': f'/shop/rider/manage/support/{rider.pk}/send/'})


@require_GET
@_admin_only
def rider_support_thread_messages(request, pk):
    return _messages_json(get_object_or_404(RiderProfile, pk=pk), 'admin', request)


@require_POST
@_admin_only
def rider_support_thread_send(request, pk):
    return _send_json(get_object_or_404(RiderProfile, pk=pk), 'admin', request)
