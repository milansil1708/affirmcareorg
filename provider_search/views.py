from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from provider_organizations.models import (
    OrganizationService,
    ProviderOrganization,
)

from .pagination import ProviderSearchPagination
from .serializers import (
    ProviderDetailSerializer,
    ProviderSearchRequestSerializer,
    ProviderSummarySerializer,
)
from .services import (
    get_public_directory_catalog,
    public_provider_queryset,
    public_provider_summary_queryset,
    search_providers,
)


class ProviderSearchView(APIView):
    permission_classes = (permissions.AllowAny,)
    pagination_class = ProviderSearchPagination

    def post(self, request):
        request_serializer = ProviderSearchRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        providers = search_providers(
            request_serializer.validated_data["filters"],
            request_serializer.validated_data["sort"],
            queryset=public_provider_summary_queryset(),
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(providers, request, view=self)
        response_serializer = ProviderSummarySerializer(page, many=True)
        return paginator.get_paginated_response(response_serializer.data)


class ProviderDetailView(generics.RetrieveAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = ProviderDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return public_provider_queryset()


class ProviderSearchOptionsView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        catalog = get_public_directory_catalog()
        return Response(
            {
                "organization_types": _choice_options(
                    ProviderOrganization.ORG_TYPE_CHOICES
                ),
                "delivery_modes": _choice_options(
                    OrganizationService.DELIVERY_MODE_CHOICES
                ),
                "age_groups": _choice_options(
                    OrganizationService.AGE_GROUP_CHOICES
                ),
                "sort_options": _choice_options(
                    ProviderSearchRequestSerializer.SORT_CHOICES
                ),
                "states": catalog["states"],
                "services": catalog["services"],
                "affirming_features": catalog["affirming_features"],
            },
            status=status.HTTP_200_OK,
        )


def _choice_options(choices):
    return [{"value": value, "label": label} for value, label in choices]
