from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
)


class ProviderOrganizationForm(forms.ModelForm):
    class Meta:
        model = ProviderOrganization
        fields = (
            "name",
            "org_type",
            "description",
            "phone",
            "email",
            "website_url",
            "booking_url",
        )
        labels = {
            "name": "Organization name",
            "org_type": "Organization type",
            "website_url": "Website URL",
            "booking_url": "Booking URL",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Organization name", "autofocus": True}
            ),
            "org_type": forms.Select(),
            "description": forms.Textarea(
                attrs={
                    "rows": 7,
                    "placeholder": "Describe your organization, approach, and care offered.",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "placeholder": "(555) 123-4567",
                    "autocomplete": "tel",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "care@example.com",
                    "autocomplete": "email",
                }
            ),
            "website_url": forms.URLInput(
                attrs={"placeholder": "https://example.com"}
            ),
            "booking_url": forms.URLInput(
                attrs={"placeholder": "https://example.com/book"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ProviderLocationForm(forms.ModelForm):
    class Meta:
        model = ProviderLocation
        fields = (
            "address_line1",
            "address_line2",
            "city",
            "state_code",
            "zip_code",
            "wheelchair_accessible",
            "gender_neutral_restrooms",
            "public_transit_notes",
        )
        labels = {
            "address_line1": "Address",
            "address_line2": "Address line 2",
            "state_code": "State",
            "zip_code": "ZIP code",
            "public_transit_notes": "Accessible by public transit",
        }
        widgets = {
            "address_line1": forms.TextInput(
                attrs={"placeholder": "Street address", "autocomplete": "address-line1"}
            ),
            "address_line2": forms.TextInput(
                attrs={"placeholder": "Suite, floor, or unit", "autocomplete": "address-line2"}
            ),
            "city": forms.TextInput(
                attrs={"placeholder": "City", "autocomplete": "address-level2"}
            ),
            "state_code": forms.TextInput(
                attrs={"placeholder": "State", "autocomplete": "address-level1"}
            ),
            "zip_code": forms.TextInput(
                attrs={"placeholder": "ZIP code", "autocomplete": "postal-code"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "accessibility-checkbox"
            else:
                field.widget.attrs["class"] = "form-control"


class OrganizationServiceForm(forms.ModelForm):
    class Meta:
        model = OrganizationService
        fields = ("service", "delivery_mode", "age_group", "note")
        labels = {
            "delivery_mode": "Delivery mode",
            "age_group": "Age group",
        }
        widgets = {
            "note": forms.TextInput(
                attrs={"placeholder": "Optional details about this service"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class RequiredOrganizationServiceFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        selected_services = []
        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", {})
            if not cleaned_data or cleaned_data.get("DELETE"):
                continue
            service = cleaned_data.get("service")
            if service:
                selected_services.append(service.pk)

        if not selected_services:
            raise ValidationError("Add at least one service.")
        if len(selected_services) != len(set(selected_services)):
            raise ValidationError("Each service can only be added once.")


OrganizationServiceFormSet = inlineformset_factory(
    ProviderOrganization,
    OrganizationService,
    form=OrganizationServiceForm,
    formset=RequiredOrganizationServiceFormSet,
    fields=("service", "delivery_mode", "age_group", "note"),
    extra=1,
    can_delete=True,
)


class ProviderFeatureSelectionForm(forms.Form):
    features = forms.ModelMultipleChoiceField(
        queryset=AffirmingFeature.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Affirming features",
        help_text="Select every feature currently available at your organization.",
    )

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        self.fields["features"].queryset = AffirmingFeature.objects.order_by("label")
        if not self.is_bound and organization:
            self.initial["features"] = organization.affirming_features.filter(
                value="yes"
            ).values_list("feature_id", flat=True)

    def save(self):
        selected_features = self.cleaned_data["features"]
        self.organization.affirming_features.all().delete()
        ProviderFeature.objects.bulk_create(
            [
                ProviderFeature(
                    provider=self.organization,
                    feature=feature,
                    value="yes",
                )
                for feature in selected_features
            ]
        )
