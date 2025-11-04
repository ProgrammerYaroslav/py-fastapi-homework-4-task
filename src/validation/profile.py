# src/validation/profile.py

from datetime import date
from io import BytesIO

from fastapi import HTTPException, status, UploadFile
from PIL import Image


def validate_name(name: str, field_name: str = "Name") -> str:
    if not name or not name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be empty.",
        )
    if not name.isalpha():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must contain only English letters.",
        )
    return name.strip().lower()


def validate_gender(gender: str) -> str:
    valid_genders = {"man", "woman", "other"}  # Example valid genders
    if gender.lower() not in valid_genders:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid gender. Must be one of {', '.join(valid_genders)}.",
        )
    return gender.lower()


def validate_birth_date(date_of_birth: date) -> date:
    today = date.today()
    age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
    if age < 18:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User must be at least 18 years old.",
        )
    if date_of_birth > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date of birth cannot be in the future.",
        )
    return date_of_birth


async def validate_image(file: UploadFile) -> UploadFile:
    if not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not determine image type."
        )

    allowed_types = ["image/jpeg", "image/png", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid image format. Only JPG, JPEG, PNG are allowed."
        )

    max_size_mb = 1
    max_size_bytes = max_size_mb * 1024 * 1024
    file.file.seek(0, 2)  # Go to the end of the file
    file_size = file.file.tell()  # Get the current position (file size)
    file.file.seek(0)  # Go back to the beginning

    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image size exceeds {max_size_mb}MB."
        )

    # Optional: Validate if it's a real image using PIL
    try:
        # Read the file content for PIL without consuming the stream for FastAPI
        file_content = await file.read()
        Image.open(BytesIO(file_content)).verify()
        await file.seek(0) # Reset file pointer for subsequent reads (e.g., S3 upload)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Corrupt or invalid image file."
        )

    return file
