import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0102_store_issue'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiderSOS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lat', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('lng', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('location_source', models.CharField(blank=True, default='', help_text='live = abhi phone se, last = rider ki aakhri maloom jagah', max_length=10)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('status', models.CharField(choices=[('open', 'Open'), ('resolved', 'Resolved')], db_index=True, default='open', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('admin_note', models.CharField(blank=True, default='', max_length=200)),
                ('delivery', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.deliveryinfo')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sos_alerts', to='app.riderprofile')),
            ],
            options={
                'verbose_name_plural': '\U0001F198 Rider SOS',
                'ordering': ['-created_at'],
            },
        ),
    ]
