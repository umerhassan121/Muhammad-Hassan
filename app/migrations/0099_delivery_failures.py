import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0098_rider_payout_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deliveryinfo',
            name='status',
            field=models.CharField(choices=[
                ('pending', '⏳ Pending'), ('assigned', '✅ Assigned'), ('picked_up', '📦 Picked Up'),
                ('in_transit', '🛵 In Transit'), ('delivered', '🎉 Delivered'),
                ('returned', '↩️ Returned to store'), ('cancelled', '❌ Cancelled')],
                default='pending', max_length=20),
        ),
        migrations.AlterField(
            model_name='ordertracking',
            name='status',
            field=models.CharField(choices=[
                ('confirmed', '✅ Confirmed'), ('processing', '⚙️ Processing'), ('packed', '📦 Packed'),
                ('rider_assigned', '🏍️ Rider Assigned'), ('ready_for_pickup', '🚶 Ready for Pickup'),
                ('out_for_delivery', '🛵 Out for Delivery'), ('delivered', '🎉 Delivered'),
                ('picked_up', '✋ Picked Up by Customer'), ('delivery_failed', '⚠️ Delivery failed'),
                ('cancelled', '❌ Cancelled')], max_length=25),
        ),
        migrations.CreateModel(
            name='DeliveryFailure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[('unreachable', 'Customer is not answering'), ('wrong_address', 'Wrong or unfindable address'), ('refused', 'Customer refused the order'), ('other', 'Other')], max_length=15)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('status', models.CharField(choices=[('waiting', 'Waiting'), ('returned', 'Returned to store'), ('closed', 'Closed')], db_index=True, default='waiting', max_length=10)),
                ('customer_ready', models.BooleanField(default=False)),
                ('reported_at', models.DateTimeField(auto_now_add=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('rider_fee', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('resolution', models.CharField(blank=True, default='', help_text='delivered / redispatched / cancelled', max_length=15)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('delivery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='failures', to='app.deliveryinfo')),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_failures', to='app.riderprofile')),
                ('sale_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_failures', to='app.saleorder')),
            ],
            options={'ordering': ['-reported_at']},
        ),
        migrations.AddConstraint(
            model_name='deliveryfailure',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'waiting')), fields=('delivery',), name='one_open_delivery_failure'),
        ),
    ]
