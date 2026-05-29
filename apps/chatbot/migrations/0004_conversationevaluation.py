# Generated manually for conversation-level evaluation support.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('chatbot', '0003_remove_selected_document_ids'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConversationEvaluation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField(choices=[(1, 'Very bad'), (2, 'Bad'), (3, 'Neutral'), (4, 'Good'), (5, 'Excellent')])),
                ('accuracy_rating', models.PositiveSmallIntegerField(blank=True, choices=[(1, 'Very bad'), (2, 'Bad'), (3, 'Neutral'), (4, 'Good'), (5, 'Excellent')], null=True)),
                ('usefulness_rating', models.PositiveSmallIntegerField(blank=True, choices=[(1, 'Very bad'), (2, 'Bad'), (3, 'Neutral'), (4, 'Good'), (5, 'Excellent')], null=True)),
                ('grounding_rating', models.PositiveSmallIntegerField(blank=True, choices=[(1, 'Very bad'), (2, 'Bad'), (3, 'Neutral'), (4, 'Good'), (5, 'Excellent')], null=True)),
                ('comment', models.TextField(blank=True)),
                ('is_pinned', models.BooleanField(default=False)),
                ('pinned_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('chat_session', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='evaluation', to='chatbot.chatsession')),
                ('pinned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pinned_conversation_evaluations', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversation_evaluations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
                'indexes': [
                    models.Index(fields=['user', '-updated_at'], name='chatbot_con_user_id_51c9ce_idx'),
                    models.Index(fields=['rating', '-updated_at'], name='chatbot_con_rating_8a66a1_idx'),
                    models.Index(fields=['is_pinned', '-updated_at'], name='chatbot_con_is_pinn_24fb0b_idx'),
                ],
            },
        ),
    ]
