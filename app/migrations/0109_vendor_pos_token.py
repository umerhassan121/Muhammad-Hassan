import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0108_sponsored_budget_stats'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorPosToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_hash', models.CharField(editable=False, max_length=64, unique=True)),
                ('prefix', models.CharField(blank=True, default='', editable=False, help_text='Token ke pehle chand harf (pehchan ke liye)', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='pos_token', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Vendor POS Token',
                'verbose_name_plural': 'Vendor POS Tokens',
            },
        ),
    ]
