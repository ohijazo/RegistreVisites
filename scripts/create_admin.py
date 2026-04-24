#!/usr/bin/env python3
"""Crea el primer usuari administrador."""
import argparse
import asyncio
import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import AdminUser
from app.services.auth import hash_password


async def main():
    parser = argparse.ArgumentParser(description="Crear usuari admin")
    parser.add_argument("--email", required=True, help="Email de l'admin")
    parser.add_argument("--name", default="Administrador", help="Nom complet")
    parser.add_argument("--password", default=None, help="Contrasenya (si no s'indica, es demana)")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("Contrasenya (mín. 12 caràcters): ")
        if len(password) < 12:
            print("ERROR: La contrasenya ha de tenir almenys 12 caràcters.")
            return

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        # Comprovar si ja existeix
        result = await session.execute(
            select(AdminUser).where(AdminUser.email == args.email)
        )
        if result.scalar_one_or_none():
            print(f"ERROR: Ja existeix un usuari amb l'email {args.email}")
            return

        user = AdminUser(
            email=args.email,
            name=args.name,
            password_hash=hash_password(password),
            role="admin",
            active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Usuari admin creat: {args.email}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
