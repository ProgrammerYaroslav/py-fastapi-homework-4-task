# src/validation/profile.py

from datetime import date
from io import BytesIO

# Імпорти для валідації на рівні маршруту
from fastapi import HTTPException, status, UploadFile
from PIL import Image

# --- Функції для валідації моделі Pydantic (викликають ValueError) ---

def validate_name(name: str, field_name: str = "Name") -> str:
    """Валідує ім'я. Має містити лише літери та не бути порожнім."""
    if not name or not name.strip():
        raise ValueError(f"{field_name} cannot be empty.")
    if not name.isalpha():
        raise ValueError(f"{field_name} must contain only English letters.")
    return name.strip().lower()

def validate_birth_date(date_of_birth: date) -> date:
    """Валідує дату народження. Користувачу має бути 18+ років."""
    today = date.today()
    age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
    if age < 18:
        raise ValueError("User must be at least 18 years old.")
    if date_of_birth > today:
        raise ValueError("Date of birth cannot be in the future.")
    return date_of_birth

# --- Функції для валідації на рівні маршруту (викликають HTTPException) ---

async def validate_image(file: UploadFile) -> UploadFile:
    """
    Валідує файл аватара. Використовується в маршруті, тому викликає HTTPException.
    """
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
    
    # Використовуємо seek/tell для перевірки розміру без повного зчитування в пам'ять
    file.file.seek(0, 2)
    file_size = file.file.tell()
    await file.seek(0) # Повертаємо покажчик на початок для подальшого читання

    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image size exceeds {max_size_mb}MB."
        )

    # Перевірка, чи це справжнє зображення
    try:
        file_content = await file.read()
        Image.open(BytesIO(file_content)).verify()
        await file.seek(0) # Знову скидаємо покажчик
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Corrupt or invalid image file."
        )

    return file
