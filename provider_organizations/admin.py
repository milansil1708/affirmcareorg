from django.contrib import admin
from django import forms
from tinymce.widgets import TinyMCE

from .models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)


class ProviderLocationInline(admin.TabularInline):
    model = ProviderLocation
    extra = 0
    fields = (
        "address_line1",
        "address_line2",
        "city",
        "state_code",
        "zip_code",
        "is_primary",
        "wheelchair_accessible",
        "gender_neutral_restrooms",
        "public_transit_notes",
    )


class OrganizationServiceInline(admin.TabularInline):
    model = OrganizationService
    extra = 0
    fields = ("service", "delivery_mode", "age_group", "note")
    autocomplete_fields = ("service",)


class ProviderFeatureInline(admin.TabularInline):
    model = ProviderFeature
    extra = 0
    fields = ("feature", "value", "verified_at", "source_url", "evidence_note")
    autocomplete_fields = ("feature",)


class ProviderOrganizationAdminForm(forms.ModelForm):
    description = forms.CharField(widget=TinyMCE())

    class Meta:
        model = ProviderOrganization
        fields = "__all__"


@admin.register(ProviderOrganization)
class ProviderOrganizationAdmin(admin.ModelAdmin):
    form = ProviderOrganizationAdminForm
    list_display = ("name", "org_type", "is_active", "phone", "email", "last_verified_at")
    list_filter = ("org_type", "is_active", "last_verified_at")
    search_fields = ("name", "description", "phone", "email", "website_url")
    readonly_fields = ("slug",)
    ordering = ("name",)
    inlines = (ProviderLocationInline, OrganizationServiceInline, ProviderFeatureInline)
    fieldsets = (
        ("Basic Info", {"fields": ("name", "slug", "org_type", "description", "is_active")}),
        ("Contact", {"fields": ("phone", "email", "website_url", "booking_url")}),
        ("Verification", {"fields": ("last_verified_at",)}),
    )


@admin.register(ProviderLocation)
class ProviderLocationAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "city",
        "state_code",
        "zip_code",
        "is_primary",
        "wheelchair_accessible",
        "gender_neutral_restrooms",
    )
    list_filter = (
        "state_code",
        "is_primary",
        "wheelchair_accessible",
        "gender_neutral_restrooms",
        "public_transit_notes",
    )
    search_fields = ("organization__name", "address_line1", "city", "zip_code")
    autocomplete_fields = ("organization",)
    ordering = ("organization__name", "state_code", "city")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    readonly_fields = ("slug",)
    ordering = ("name",)


@admin.register(OrganizationService)
class OrganizationServiceAdmin(admin.ModelAdmin):
    list_display = ("organization", "service", "delivery_mode", "age_group")
    list_filter = ("delivery_mode", "age_group", "organization__org_type")
    search_fields = ("organization__name", "service__name", "note")
    autocomplete_fields = ("organization", "service")
    ordering = ("organization__name", "service__name")


@admin.register(AffirmingFeature)
class AffirmingFeatureAdmin(admin.ModelAdmin):
    list_display = ("label", "code")
    search_fields = ("label", "description")
    readonly_fields = ("code",)
    ordering = ("label",)


@admin.register(ProviderFeature)
class ProviderFeatureAdmin(admin.ModelAdmin):
    list_display = ("provider", "feature", "value", "verified_at")
    list_filter = ("value", "verified_at", "feature")
    search_fields = ("provider__name", "feature__label", "evidence_note", "source_url")
    autocomplete_fields = ("provider", "feature")
    ordering = ("provider__name", "feature__label")
