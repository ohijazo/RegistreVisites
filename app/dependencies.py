from fastapi import Cookie, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from app.config import settings
from app.db.database import get_db
from app.db.models import AdminUser


async def get_current_admin(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not access_token:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    try:
        payload = jwt.decode(access_token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        iat = payload.get("iat", 0)
        if not user_id:
            raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    except JWTError:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id, AdminUser.active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})

    # Invalidar tokens emesos abans de l'últim logout (o reset de password)
    if user.last_logout_at and iat < int(user.last_logout_at.timestamp()):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})

    return user


def require_role(*roles: str):
    async def checker(admin: AdminUser = Depends(get_current_admin)):
        if admin.role not in roles:
            raise HTTPException(status_code=403, detail="No teniu permisos per a aquesta acció.")
        return admin
    return checker
