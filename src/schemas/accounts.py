# src/schemas/profiles.py

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from fastapi import UploadFile

from src.database.models.accounts import GenderEnum
from src.validation.profile import (
    validate_name,
    validate_gender,
    validate_birth_date,
)


class ProfileCreateSchema(BaseModel):
    first_name: str = Field(..., description="User's first name")
    last_name: str = Field(..., description="User's last name")
    gender: GenderEnum = Field(..., description="User's gender")
    date_of_birth: date = Field(..., description="User's date of birth (YYYY-MM-DD)")
    info: Optional[str] = Field(None, description="Additional information about the user")
    # avatar: UploadFile # This will be handled directly in the route for Form data

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        return validate_name(v, "First Name")

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, v: str) -> str:
        return validate_name(v, "Last Name")

    @field_validator("gender")
    @classmethod
    def validate_gender_enum(cls, v: GenderEnum) -> GenderEnum:
        # Pydantic enum validation handles this implicitly, but you can add explicit logic if GenderEnum allows 'other' string directly
        # For example, if GenderEnum values are strings, you might do:
        # return GenderEnum(validate_gender(v.value))
        return v # If GenderEnum is already enforced, this is fine

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth_value(cls, v: date) -> date:
        return validate_birth_date(v)

    @field_validator("info")
    @classmethod
    def validate_info(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Info cannot be empty or consist only of spaces.",
            )
        return v.strip() if v else None


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: GenderEnum
    date_of_birth: date
    info: Optional[str] = None
    avatar: Optional[str] = None # This will be a URL

    class Config:
        from_attributes = True
