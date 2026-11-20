import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0095_notification_features'),
    ]

    operations = [
        migrations.CreateModel(
            name='FcmDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.TextField()),
                ('token_hash', models.CharField(editable=False, max_length=64, unique=True)),
                ('app', models.CharField(default='rider', max_length=20)),
                ('platform', models.CharField(default='android', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_success_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fcm_devices', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'FCM device',
                'verbose_name_plural': 'FCM devices',
                'ordering': ['-created_at'],
            },
        ),
    ]
