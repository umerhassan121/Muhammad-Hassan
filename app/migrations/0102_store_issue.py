import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0101_delivery_arrival_times'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreIssue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[('not_ready', 'Order is not ready yet'), ('closed', 'Store is closed'), ('missing_items', 'Items are missing in the order'), ('other', 'Other')], max_length=15)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('reported_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('delivery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='store_issues', to='app.deliveryinfo')),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='store_issues', to='app.riderprofile')),
                ('sale_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='store_issues', to='app.saleorder')),
            ],
            options={
                'verbose_name_plural': '\U0001F3EA Store issues',
                'ordering': ['-reported_at'],
            },
        ),
    ]
