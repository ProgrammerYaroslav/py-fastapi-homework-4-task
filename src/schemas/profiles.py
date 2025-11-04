# src/schemas/profiles.py

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from fastapi import Form, Depends

# Виправлено імпорти: видалено 'src.'
from database.models.accounts import GenderEnum
from validation.profile import (
    validate_name,
    validate_birth_date,
    validate_gender,  # <-- Додано імпорт
)


class ProfileCreateSchema(BaseModel):
    first_name: str = Field(..., description="User's first name")
    last_name: str = Field(..., description="User's last name")
    gender: GenderEnum = Field(..., description="User's gender")
    date_of_birth: date = Field(..., description="User's date of birth (YYYY-MM-DD)")
    info: Optional[str] = Field(None, description="Additional information about the user")

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
    def validate_gender_value(cls, v: GenderEnum) -> GenderEnum:
        """
        НОВИЙ ВАЛІДАТОР: Використовує функцію validate_gender 
        для перевірки значення enum.
        """
        # Pydantic вже перетворив вхідний рядок на Enum.
        # Ми валідуємо строкове .value() цього Enum.
        validate_gender(v.value)
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth_value(cls, v: date) -> date:
        return validate_birth_date(v)

    @field_validator("info")
    @classmethod
    def validate_info(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Info cannot be empty or consist only of spaces.")
        return v.strip() if v else None
    
    @classmethod
    def as_form(
        cls,
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: GenderEnum = Form(...),
        date_of_birth: date = Form(...),
        info: Optional[str] = Form(None),
    ):
        return cls(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
        )


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: GenderEnum
    date_of_birth: date
    info: Optional[str] = None
    avatar: Optional[str] = None

    class Config:
        from_attributes = True
