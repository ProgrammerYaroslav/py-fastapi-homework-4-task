# src/routes/accounts.py

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.dependencies import (
    get_db,
    get_jwt_auth_manager,
    get_settings,
    get_accounts_email_notificator,
)
from src.config.settings import BaseAppSettings
from src.database.models.accounts import (
    UserModel,
    UserGroupModel,
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
)
from src.database.validators.accounts import (
    validate_password_strength,
    validate_email_is_unique,
)
from src.exceptions.security import (
    IncorrectCredentialsError,
    TokenExpiredError,
    TokenValidationException,
    InactiveUserError,
)
from src.notifications.interfaces import EmailSenderInterface
from src.routes.mixins import AuthRouterMixin
from src.schemas.accounts import (
    UserRegistrationSchema,
    TokenBaseSchema,
    UserLoginSchema,
    UserBaseSchema,
    TokensSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
    UserGroupEnum,
)
from src.security.interfaces import JWTAuthManagerInterface
from src.security.passwords import PasswordManager

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post(
    "/register/",
    response_model=UserBaseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Registers a new user and sends an activation email.",
)
async def register_user(
    data: UserRegistrationSchema,
    db: Annotated[AsyncSession, Depends(get_db)],
    password_manager: Annotated[PasswordManager, Depends(PasswordManager)],
    email_sender: Annotated[
        EmailSenderInterface, Depends(get_accounts_email_notificator)
    ],
    background_tasks: BackgroundTasks,
    settings: Annotated[BaseAppSettings, Depends(get_settings)],
) -> UserModel:
    await validate_email_is_unique(db, data.email)
    validate_password_strength(data.password)

    hashed_password = password_manager.hash_password(data.password)

    user_group = await db.scalar(
        select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
    )
    if not user_group:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user group not found.",
        )

    user = UserModel(
        email=data.email, hashed_password=hashed_password, group_id=user_group.id
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    activation_token_value = str(uuid.uuid4())
    activation_token = ActivationTokenModel(
        token=activation_token_value, user_id=user.id
    )
    db.add(activation_token)
    await db.commit()
    await db.refresh(activation_token)

    # EMAIL NOTIFICATION: Send activation email
    activation_link = (
        f"{settings.ACTIVATION_FRONTEND_URL}/accounts/activate/{activation_token_value}"
    ) # Assumes you have ACTIVATION_FRONTEND_URL in your settings
    background_tasks.add_task(
        email_sender.send_activation_request_email,
        user.email,
        activation_link,
    )

    return user


@router.post(
    "/activate/{token}/",
    response_model=UserBaseSchema,
    summary="Activate user account",
    description="Activates a user's account using a valid activation token and sends a completion email.",
)
async def activate_account(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    email_sender: Annotated[
        EmailSenderInterface, Depends(get_accounts_email_notificator)
    ],
    background_tasks: BackgroundTasks,
    settings: Annotated[BaseAppSettings, Depends(get_settings)],
) -> UserModel:
    activation_token = await db.scalar(
        select(ActivationTokenModel).where(
            ActivationTokenModel.token == token,
            ActivationTokenModel.expires_at > datetime.utcnow(),
        )
    )

    if not activation_token:
        raise TokenExpiredError()

    user = await db.scalar(
        select(UserModel).where(UserModel.id == activation_token.user_id)
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    user.is_active = True
    await db.delete(activation_token)  # Token is single-use
    await db.commit()
    await db.refresh(user)

    # EMAIL NOTIFICATION: Send activation complete email
    login_link = f"{settings.LOGIN_FRONTEND_URL}/accounts/login" # Assumes you have LOGIN_FRONTEND_URL in your settings
    background_tasks.add_task(
        email_sender.send_activation_complete_email,
        user.email,
        login_link,
    )

    return user


@router.post(
    "/password/reset/request/",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset token",
    description="Requests a password reset token to be sent to the user's email.",
)
async def request_password_reset_token(
    data: PasswordResetRequestSchema,
    db: Annotated[AsyncSession, Depends(get_db)],
    email_sender: Annotated[
        EmailSenderInterface, Depends(get_accounts_email_notificator)
    ],
    background_tasks: BackgroundTasks,
    settings: Annotated[BaseAppSettings, Depends(get_settings)],
):
    user = await db.scalar(select(UserModel).where(UserModel.email == data.email))

    if not user:
        # Prevent email enumeration: return 200 OK even if user doesn't exist
        return {"message": "If a user with that email exists, a reset link has been sent."}

    # Clean up any existing password reset tokens for the user
    await db.execute(
        PasswordResetTokenModel.__table__.delete().where(
            PasswordResetTokenModel.user_id == user.id
        )
    )
    await db.commit()

    reset_token_value = str(uuid.uuid4())
    password_reset_token = PasswordResetTokenModel(
        token=reset_token_value, user_id=user.id
    )
    db.add(password_reset_token)
    await db.commit()
    await db.refresh(password_reset_token)

    # EMAIL NOTIFICATION: Send password reset request email
    reset_link = f"{settings.PASSWORD_RESET_FRONTEND_URL}/accounts/password/reset/{reset_token_value}" # Assumes you have PASSWORD_RESET_FRONTEND_URL in your settings
    background_tasks.add_task(
        email_sender.send_password_reset_request_email,
        user.email,
        reset_link,
    )

    return {"message": "Password reset link sent successfully."}


@router.post(
    "/password/reset/{token}/",
    status_code=status.HTTP_200_OK,
    summary="Reset user password",
    description="Resets the user's password using a valid reset token and sends a completion email.",
)
async def reset_password(
    token: str,
    data: PasswordResetSchema,
    db: Annotated[AsyncSession, Depends(get_db)],
    password_manager: Annotated[PasswordManager, Depends(PasswordManager)],
    email_sender: Annotated[
        EmailSenderInterface, Depends(get_accounts_email_notificator)
    ],
    background_tasks: BackgroundTasks,
    settings: Annotated[BaseAppSettings, Depends(get_settings)],
):
    validate_password_strength(data.new_password)

    password_reset_token = await db.scalar(
        select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.token == token,
            PasswordResetTokenModel.expires_at > datetime.utcnow(),
        )
    )

    if not password_reset_token:
        raise TokenExpiredError()

    user = await db.scalar(
        select(UserModel).where(UserModel.id == password_reset_token.user_id)
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    user.hashed_password = password_manager.hash_password(data.new_password)
    await db.delete(password_reset_token)  # Token is single-use
    await db.commit()
    await db.refresh(user)

    # EMAIL NOTIFICATION: Send password reset complete email
    login_link = f"{settings.LOGIN_FRONTEND_URL}/accounts/login" # Assumes you have LOGIN_FRONTEND_URL in your settings
    background_tasks.add_task(
        email_sender.send_password_reset_complete_email,
        user.email,
        login_link,
    )

    return {"message": "Password has been reset successfully."}


# Other endpoints like login, refresh token, logout, etc., would be below this
# For brevity, I'm only including the ones needing email notifications.
# You might also want to inherit from AuthRouterMixin if applicable, as in the original structure.
class AccountsRouter(AuthRouterMixin):
    @router.post(
        "/login/",
        response_model=TokensSchema,
        summary="Log in user",
        description="Authenticates a user and returns access and refresh tokens.",
    )
    async def login(
        self,
        data: UserLoginSchema,
        db: Annotated[AsyncSession, Depends(get_db)],
        password_manager: Annotated[PasswordManager, Depends(PasswordManager)],
        jwt_manager: Annotated[
            JWTAuthManagerInterface, Depends(get_jwt_auth_manager)
        ],
    ) -> TokensSchema:
        user = await db.scalar(select(UserModel).where(UserModel.email == data.email))

        if not user or not password_manager.verify_password(
            data.password, user.hashed_password
        ):
            raise IncorrectCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        access_token = jwt_manager.create_access_token(
            data={"sub": str(user.id), "email": user.email, "group": user.group.name}
        )
        refresh_token = jwt_manager.create_refresh_token(
            data={"sub": str(user.id), "email": user.email, "group": user.group.name}
        )

        refresh_token_db = RefreshTokenModel.create(
            token=refresh_token, user_id=user.id
        )
        db.add(refresh_token_db)
        await db.commit()

        return TokensSchema(access_token=access_token, refresh_token=refresh_token)

    @router.post(
        "/token/refresh/",
        response_model=TokensSchema,
        summary="Refresh access token",
        description="Refreshes an expired access token using a valid refresh token.",
    )
    async def refresh_token(
        self,
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db)],
        jwt_manager: Annotated[
            JWTAuthManagerInterface, Depends(get_jwt_auth_manager)
        ],
    ) -> TokensSchema:
        refresh_token_value = self.get_token(request)
        payload = jwt_manager.decode_token(refresh_token_value)
        user_id = payload.get("sub")

        refresh_token_db = await db.scalar(
            select(RefreshTokenModel).where(
                RefreshTokenModel.token == refresh_token_value,
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.expires_at > datetime.utcnow(),
            )
        )

        if not refresh_token_db:
            raise TokenExpiredError()

        user = await db.scalar(select(UserModel).where(UserModel.id == user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
            )

        new_access_token = jwt_manager.create_access_token(
            data={"sub": str(user.id), "email": user.email, "group": user.group.name}
        )
        # Optionally, generate a new refresh token and invalidate the old one for better security (rotate refresh tokens)
        new_refresh_token = jwt_manager.create_refresh_token(
            data={"sub": str(user.id), "email": user.email, "group": user.group.name}
        )
        await db.delete(refresh_token_db)
        new_refresh_token_db = RefreshTokenModel.create(
            token=new_refresh_token, user_id=user.id
        )
        db.add(new_refresh_token_db)
        await db.commit()

        return TokensSchema(
            access_token=new_access_token, refresh_token=new_refresh_token
        )

    @router.post(
        "/logout/",
        status_code=status.HTTP_200_OK,
        summary="Log out user",
        description="Logs out the user by invalidating the refresh token.",
    )
    async def logout(
        self,
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db)],
        jwt_manager: Annotated[
            JWTAuthManagerInterface, Depends(get_jwt_auth_manager)
        ],
    ):
        refresh_token_value = self.get_token(request)
        payload = jwt_manager.decode_token(refresh_token_value)
        user_id = payload.get("sub")

        refresh_token_db = await db.scalar(
            select(RefreshTokenModel).where(
                RefreshTokenModel.token == refresh_token_value,
                RefreshTokenModel.user_id == user_id,
            )
        )

        if refresh_token_db:
            await db.delete(refresh_token_db)
            await db.commit()
        else:
            raise TokenValidationException("Refresh token not found or already logged out.")

        return {"message": "Logged out successfully."}


accounts_router = AccountsRouter()
