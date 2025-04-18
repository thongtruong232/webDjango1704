# Generated by Django 3.2.8 on 2025-04-14 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='useractivity',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='useractivity',
            name='is_active',
            field=models.BooleanField(default=True, null=True),
        ),
        migrations.AddField(
            model_name='useractivity',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name='useractivity',
            name='user_agent',
            field=models.TextField(blank=True, null=True),
        ),
    ]
