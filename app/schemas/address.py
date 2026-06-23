from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import ORMModel


class AddressBase(ORMModel):
    title: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=120)
    street: str = Field(min_length=2, max_length=255)
    apartment: str | None = Field(default=None, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    note: str | None = Field(default=None, max_length=500)
    is_default: bool = False

    @model_validator(mode="after")
    def validate_coordinates(self) -> "AddressBase":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be sent together")
        return self


class AddressCreate(AddressBase):
    pass


class AddressUpdate(ORMModel):
    title: str | None = Field(default=None, min_length=2, max_length=80)
    city: str | None = Field(default=None, min_length=2, max_length=120)
    street: str | None = Field(default=None, min_length=2, max_length=255)
    apartment: str | None = Field(default=None, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    note: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None

    @model_validator(mode="after")
    def validate_coordinates(self) -> "AddressUpdate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be sent together")
        return self


class AddressOut(AddressBase):
    id: UUID
    created_at: datetime
