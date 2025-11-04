# src/routes/profiles.py

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.dependencies import (
    get_db,
    get_jwt_auth_manager,
    get_s3_storage_client,
    get_settings,
)
from src.config.settings import BaseAppSettings
from src.database.models.accounts import UserModel, UserProfileModel, UserGroupEnum
# Оновлені імпорти схем
from src.schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from src.security.interfaces import JWTAuthManagerInterface
from src.security.token_manager import TokenPayload
from src.storages.interfaces import S3StorageInterface
from src.exceptions.security import InactiveUserError
from src.routes.mixins import AuthRouterMixin
# Нам потрібен лише валідатор для зображення
from src.validation.profile import validate_image


router = APIRouter(prefix="/users", tags=["Profiles"])


class ProfilesRouter(AuthRouterMixin):
    @router.post(
        "/{user_id}/profile/",
        response_model=ProfileResponseSchema,
        status_code=status.HTTP_201_CREATED,
        summary="Create user profile",
        description="Creates a profile for a specified user, including avatar upload to S3.",
    )
    async def create_user_profile(
        self,
        user_id: int,
        # ВИПРАВЛЕНО: Використовуємо Pydantic для валідації форми
        profile_data: ProfileCreateSchema = Depends(ProfileCreateSchema.as_form),
        # Аватар обробляється окремо
        avatar: UploadFile = Form(...),
        db: Annotated[AsyncSession, Depends(get_db)],
        jwt_manager: Annotated[
            JWTAuthManagerInterface, Depends(get_jwt_auth_manager)
        ],
        s3_client: Annotated[S3StorageInterface, Depends(get_s3_storage_client)],
        settings: Annotated[BaseAppSettings, Depends(get_settings)],
    ) -> UserProfileModel:
        
        # 1. Валідація токена та Авторизація (без змін)
        current_user_payload: TokenPayload = self.get_current_user_payload(self.request, jwt_manager)
        if current_user_payload.group != UserGroupEnum.ADMIN and int(current_user_payload.sub) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this profile.",
            )

        # 2. Перевірка існування та статусу користувача (без змін)
        user = await db.scalar(
            select(UserModel)
            .where(UserModel.id == user_id)
            .options(AuthRouterMixin.USER_GROUP_LOAD_OPTIONS)
        )
        if not user or not user.is_active:
            raise InactiveUserError()

        # 3. Перевірка наявності профілю (без змін)
        existing_profile = await db.scalar(
            select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        )
        if existing_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has a profile.",
            )

        # 4. Валідація аватара та завантаження S3
        # Валідація Pydantic для profile_data вже ВІДБУЛАСЯ!
        # Нам потрібно вручну валідувати лише аватар.
        validated_avatar_file = await validate_image(avatar)

        avatar_filename = f"avatars/{user_id}_avatar.{validated_avatar_file.filename.split('.')[-1]}"
        
        try:
            await validated_avatar_file.seek(0)
            await s3_client.upload_file(
                file_object=validated_avatar_file.file,
                object_name=avatar_filename,
                content_type=validated_avatar_file.content_type,
            )
            avatar_url = f"{settings.S3_STORAGE_ENDPOINT}/{settings.S3_BUCKET_NAME}/{avatar_filename}"
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload avatar. Please try again later.",
            )

        # 5. Створення профілю
        # Використовуємо валідовані дані з profile_data
        profile = UserProfileModel(
            user_id=user_id,
            **profile_data.model_dump(), # Розпаковуємо валідовані дані
            avatar=avatar_url,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        return profile


profiles_router = ProfilesRouter()
