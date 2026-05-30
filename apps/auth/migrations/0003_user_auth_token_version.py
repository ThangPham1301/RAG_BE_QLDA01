from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apps_auth', '0002_user_two_factor_challenge'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='auth_token_version',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
