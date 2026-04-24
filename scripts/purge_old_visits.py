#!/usr/bin/env python3
"""Elimina visites amb més de 2 anys (RGPD). Pensat per executar-se via cron."""
import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import Visit, AuditLog


async def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=730)  # 2 anys
    print(f"Eliminant visites anteriors a {cutoff.strftime('%Y-%m-%d')}...")

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        # Primer eliminar audit logs associats
        old_visit_ids = select(Visit.id).where(Visit.checked_in_at < cutoff)
        await session.execute(
            delete(AuditLog).where(AuditLog.visit_id.in_(old_visit_ids))
        )

        # Eliminar visites
        result = await session.execute(
            delete(Visit).where(Visit.checked_in_at < cutoff)
        )
        count = result.rowcount
        await session.commit()

    print(f"Eliminades {count} visites.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
