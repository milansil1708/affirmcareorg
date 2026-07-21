from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OrganizationType = Literal[
    "clinic",
    "hospital_program",
    "telehealth",
    "private_practice",
    "nonprofit",
]
DeliveryMode = Literal["in_person", "telehealth", "both"]
AgeGroup = Literal["adult", "youth", "all"]
SortOption = Literal[
    "name",
    "-name",
    "last_verified_at",
    "-last_verified_at",
]
ChatIntent = Literal[
    "search_providers",
    "provider_details",
    "clarification",
    "unsupported_request",
]
UnsupportedCategory = Literal[
    "medical_advice",
    "emergency",
    "insurance",
    "ratings_reviews",
    "pricing",
    "languages",
    "availability",
    "database_or_private_data",
    "prompt_injection",
    "out_of_scope",
]


class ChatFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str | None = Field(max_length=200)
    org_types: list[OrganizationType] = Field(max_length=20)
    city: str | None = Field(max_length=100)
    state_code: str | None = Field(max_length=100)
    zip_code: str | None = Field(max_length=20)
    service_slugs: list[str] = Field(max_length=20)
    delivery_modes: list[DeliveryMode] = Field(max_length=20)
    age_groups: list[AgeGroup] = Field(max_length=20)
    wheelchair_accessible: bool | None
    gender_neutral_restrooms: bool | None
    public_transit_access: bool | None
    affirming_feature_codes: list[str] = Field(max_length=20)
    verified_after: datetime | None
    has_booking_url: bool | None
    has_website_url: bool | None

    def to_search_data(self):
        data = self.model_dump(exclude_none=True)
        return {key: value for key, value in data.items() if value != []}


class ChatInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: ChatIntent
    filters: ChatFilters
    sort: SortOption
    provider_slug: str | None = Field(max_length=255)
    needs_clarification: bool
    clarification_question: str | None = Field(max_length=300)
    unsupported_category: UnsupportedCategory | None
