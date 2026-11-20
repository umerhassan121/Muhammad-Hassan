import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0099_delivery_failures'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiderSupportMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sender_role', models.CharField(choices=[('rider', 'Rider'), ('admin', 'Admin')], max_length=6)),
                ('message', models.CharField(max_length=1000)),
                ('is_read', models.BooleanField(default=False, help_text='Samne wale ne parh liya')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_messages', to='app.riderprofile')),
                ('sender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['id']},
        ),
        migrations.AddIndex(
            model_name='ridersupportmessage',
            index=models.Index(fields=['rider', 'id'], name='app_ridsup_rider_id_idx'),
        ),
    ]
