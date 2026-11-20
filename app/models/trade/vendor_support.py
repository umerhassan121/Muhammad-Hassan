"""Models: trade/vendor_support - vendor ka support ticket (shop admin se madad) aur us ka jawab.

Ek ticket = ek masla; us ke andar vendor aur admin ke paigham (SupportMessage) baari baari.
Status: open (admin ke jawab ka intezar) -> answered (admin ne jawab diya) -> closed.
"""
from django.db import models


class SupportTicket(models.Model):
    CATEGORY_CHOICES = [
        ('orders', 'Orders'),
        ('payments', 'Payments / payouts'),
        ('menu', 'Menu / products'),
        ('store', 'Store settings'),
        ('account', 'Account / documents'),
        ('technical', 'App / technical problem'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open (waiting for support)'),
        ('answered', 'Answered'),
        ('closed', 'Closed'),
    ]

    profile = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='support_tickets')
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    subject = models.CharField(max_length=120)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default='other')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', db_index=True)
    vendor_unread = models.BooleanField(default=False, help_text="Admin ka naya jawab jo vendor ne abhi nahi dekha")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        verbose_name = 'Support Ticket'
        verbose_name_plural = '3.6 Vendor Support Tickets'
        indexes = [models.Index(fields=['status', 'updated_at'], name='support_status_upd_idx')]

    def __str__(self):
        return f"{self.number} - {self.subject}"

    @property
    def number(self):
        return f"T-{self.pk}" if self.pk else "T-new"

    @property
    def is_closed(self):
        return self.status == 'closed'


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    is_admin = models.BooleanField(default=False)
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Support Message'
        verbose_name_plural = 'Support Messages'

    def __str__(self):
        return f"{self.ticket_id}: {'support' if self.is_admin else 'vendor'}"
