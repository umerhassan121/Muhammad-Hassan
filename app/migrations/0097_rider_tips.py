import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0096_fcm_device'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiderTip',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.customer')),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tips', to='app.riderprofile')),
                ('sale_order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rider_tip', to='app.saleorder')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterField(
            model_name='wallettransaction',
            name='kind',
            field=models.CharField(choices=[
                ('topup', 'Top-up (admin ne jama kiya)'), ('adjust', 'Adjustment (admin)'),
                ('spend', 'Order mein kharch'), ('refund', 'Order cancel - wapas'),
                ('cashback', 'Cashback reward'), ('points', 'Loyalty points se credit'),
                ('pro', 'Pro membership ki payment'), ('dispute', 'Dispute refund'),
                ('referral', 'Referral reward (dost laaya)'), ('refbonus', 'Referral welcome bonus'),
                ('giftcard', 'Gift card redeem'), ('tip', 'Rider ko tip')], max_length=10),
        ),
    ]
