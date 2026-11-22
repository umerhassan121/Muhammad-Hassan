from django.contrib import admin

from .models import IncomeSource


@admin.register(IncomeSource)
class IncomeSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'owner', 'is_active', 'created_at')
    list_filter = ('source_type', 'is_active')
    search_fields = ('name', 'owner__username')
