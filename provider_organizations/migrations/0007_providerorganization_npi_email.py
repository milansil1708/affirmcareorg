from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("provider_organizations", "0006_providerorganizationclaim_unique_pending_claim_per_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerorganization",
            name="npi",
            field=models.CharField(
                max_length=10,
                unique=True,
                blank=True,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="providerorganization",
            name="email",
            field=models.EmailField(
                max_length=100,
                blank=True,
                null=True,
            ),
        ),
    ]
