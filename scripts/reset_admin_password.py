#!/usr/bin/env python3
"""Reseteja la contrasenya d'un usuari admin existent."""
import argparse
import asyncio
import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import AdminUser
from app.services.auth import hash_password


async def main():
    parser = argparse.ArgumentParser(description="Resetejar contrasenya d'un admin")
    parser.add_argument("--email", required=True, help="Email de l'admin")
    parser.add_argument("--password", default=None, help="Nova contrasenya (si no s'indica, es demana)")
    parser.add_argument("--activate", action="store_true", help="Reactiva l'usuari si està desactivat")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("Nova contrasenya (mín. 12 caràcters): ")
        confirm = getpass.getpass("Repeteix la contrasenya: ")
        if password != confirm:
            print("ERROR: Les contrasenyes no coincideixen.")
            return
    if len(password) < 12:
        print("ERROR: La contrasenya ha de tenir almenys 12 caràcters.")
        return

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.email == args.email)
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"ERROR: No existeix cap usuari amb l'email {args.email}")
            return

        user.password_hash = hash_password(password)
        if args.activate:
            user.active = True
        await session.commit()
        status = "activa" if user.active else "DESACTIVADA"
        print(f"Contrasenya resetejada per {user.email} (compte: {status})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
