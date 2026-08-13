from django.db import models
from django.conf import settings
from django.db.models import Q
from autoslug import AutoSlugField


# Create your models here.
class ProviderOrganization(models.Model):

    ORG_TYPE_CHOICES = [
        ('clinic', 'Clinic'),
        ('hospital_program', 'Hospital Program'),
        ('telehealth', 'Telehealth'),
        ('private_practice', 'Private Practice'),
        ('nonprofit', 'Nonprofit'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="provider_organizations",
        blank=True,
        null=True,
    )

    name = models.CharField(max_length=100)

    # NPI number from the CMS NPPES public dataset.
    # Used to identify and prevent duplicate provider records.
    npi = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        null=True,
    )

    slug = AutoSlugField(
        populate_from="name",
        unique=True
    )

    org_type = models.CharField(
        max_length=50,
        choices=ORG_TYPE_CHOICES
    )

    description = models.TextField()

    website_url = models.URLField(
        blank=True,
        null=True
    )

    booking_url = models.URLField(
        blank=True,
        null=True
    )

    phone = models.CharField(
        max_length=20
    )

    email = models.EmailField(
        max_length=100
    )

    is_active = models.BooleanField(
        default=True
    )

    last_verified_at = models.DateTimeField(
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name


class ProviderOrganizationClaim(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        related_name="claim_requests",
    )

    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="provider_claim_requests",
        blank=True,
        null=True,
    )

    claimant_email = models.EmailField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    admin_note = models.TextField(
        blank=True
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_provider_claims",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    reviewed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("-created_at",)

        constraints = (
            models.UniqueConstraint(
                fields=("organization", "claimant"),
                condition=Q(status="pending"),
                name="unique_pending_provider_claim",
            ),

            models.UniqueConstraint(
                fields=("claimant",),
                condition=Q(status="pending"),
                name="unique_pending_claim_per_user",
            ),
        )

    def __str__(self):
        return (
            f"{self.organization} - "
            f"{self.claimant_email} "
            f"({self.get_status_display()})"
        )


class ProviderLocation(models.Model):
    organization = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        related_name='locations'
    )

    address_line1 = models.CharField(
        max_length=255
    )

    address_line2 = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    city = models.CharField(
        max_length=100
    )

    state_code = models.CharField(
        max_length=100
    )

    zip_code = models.CharField(
        max_length=20
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True
    )

    is_primary = models.BooleanField(
        default=False
    )

    wheelchair_accessible = models.BooleanField(
        default=False
    )

    gender_neutral_restrooms = models.BooleanField(
        default=False
    )

    public_transit_notes = models.BooleanField(
        default=False
    )

    def __str__(self):
        return (
            f"{self.organization.name} - "
            f"{self.address_line1}, {self.city}"
        )


class Service(models.Model):
    slug = AutoSlugField(
        populate_from="name",
        unique=True
    )

    name = models.CharField(
        max_length=100,
    )

    def __str__(self):
        return self.name


class OrganizationService(models.Model):
    organization = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        related_name='services'
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='organizations'
    )

    DELIVERY_MODE_CHOICES = [
        ('in_person', 'In Person'),
        ('telehealth', 'Telehealth'),
        ('both', 'Both'),
    ]

    AGE_GROUP_CHOICES = [
        ('adult', 'Adult'),
        ('youth', 'Youth'),
        ('all', 'All Ages'),
    ]

    delivery_mode = models.CharField(
        max_length=20,
        choices=DELIVERY_MODE_CHOICES,
    )

    age_group = models.CharField(
        max_length=20,
        choices=AGE_GROUP_CHOICES,
    )

    note = models.TextField(
        blank=True,
        null=True
    )

    def __str__(self):
        return (
            f"{self.organization.name} - "
            f"{self.service.name}"
        )


class AffirmingFeature(models.Model):
    code = AutoSlugField(
        populate_from="label",
        unique=True
    )

    label = models.CharField(
        max_length=120
    )

    description = models.TextField()

    def __str__(self):
        return self.label


class ProviderFeature(models.Model):
    VALUE_CHOICES = [
        ("yes", "Yes"),
        ("no", "No"),
        ("unknown", "Unknown"),
    ]

    provider = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        related_name='affirming_features'
    )

    feature = models.ForeignKey(
        AffirmingFeature,
        on_delete=models.CASCADE,
        related_name='providers'
    )

    value = models.CharField(
        max_length=20,
        choices=VALUE_CHOICES,
        default="unknown"
    )

    evidence_note = models.TextField(
        blank=True,
    )

    source_url = models.URLField(
        blank=True,
        null=True
    )

    verified_at = models.DateTimeField(
        blank=True,
        null=True
    )
