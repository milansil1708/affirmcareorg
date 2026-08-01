from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("provider_chat", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatturn",
            name="intent",
            field=models.CharField(
                choices=[
                    ("informational", "Informational"),
                    ("search_providers", "Search providers"),
                    ("provider_details", "Provider details"),
                    ("clarification", "Clarification"),
                ],
                max_length=32,
            ),
        ),
    ]
