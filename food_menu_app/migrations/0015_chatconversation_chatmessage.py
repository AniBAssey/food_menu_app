import secrets

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('food_menu_app', '0014_customermessage'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatConversation',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'session_token',
                    models.CharField(
                        default=secrets.token_urlsafe,
                        max_length=64,
                        unique=True,
                    ),
                ),
                ('name', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254)),
                ('is_open', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('-updated_at',),
            },
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'sender',
                    models.CharField(
                        choices=[
                            ('visitor', 'Visitor'),
                            ('bot', 'Chatbot'),
                            ('admin', 'Staff'),
                        ],
                        max_length=10,
                    ),
                ),
                ('message', models.CharField(max_length=2000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'conversation',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='messages',
                        to='food_menu_app.chatconversation',
                    ),
                ),
            ],
            options={
                'ordering': ('id',),
            },
        ),
    ]
