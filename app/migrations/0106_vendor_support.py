import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0105_order_accept_ready_times'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=120)),
                ('category', models.CharField(choices=[('orders', 'Orders'), ('payments', 'Payments / payouts'), ('menu', 'Menu / products'), ('store', 'Store settings'), ('account', 'Account / documents'), ('technical', 'App / technical problem'), ('other', 'Other')], default='other', max_length=12)),
                ('status', models.CharField(choices=[('open', 'Open (waiting for support)'), ('answered', 'Answered'), ('closed', 'Closed')], db_index=True, default='open', max_length=10)),
                ('vendor_unread', models.BooleanField(default=False, help_text='Admin ka naya jawab jo vendor ne abhi nahi dekha')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_tickets', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Support Ticket',
                'verbose_name_plural': '3.6 Vendor Support Tickets',
                'ordering': ['-updated_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='SupportMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_admin', models.BooleanField(default=False)),
                ('body', models.TextField(max_length=2000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='app.supportticket')),
            ],
            options={
                'verbose_name': 'Support Message',
                'verbose_name_plural': 'Support Messages',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='supportticket',
            index=models.Index(fields=['status', 'updated_at'], name='support_status_upd_idx'),
        ),
    ]
