#!/usr/bin/env python3
"""Exporta visites a Excel o CSV per línia de comandes."""
import argparse
import asyncio
from datetime import date, datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import Visit
from app.services.export import visits_to_excel, visits_to_csv


async def main():
    parser = argparse.ArgumentParser(description="Exportar visites")
    parser.add_argument("--from", dest="date_from", required=True, help="Data inici (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", required=True, help="Data fi (YYYY-MM-DD)")
    parser.add_argument("--format", choices=["xlsx", "csv"], default="xlsx", help="Format de sortida")
    parser.add_argument("--output", default=None, help="Fitxer de sortida")
    args = parser.parse_args()

    dt_from = datetime.combine(date.fromisoformat(args.date_from), datetime.min.time(), tzinfo=timezone.utc)
    dt_to = datetime.combine(date.fromisoformat(args.date_to) + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        result = await session.execute(
            select(Visit)
            .options(selectinload(Visit.department))
            .where(and_(Visit.checked_in_at >= dt_from, Visit.checked_in_at < dt_to))
            .order_by(Visit.checked_in_at.desc())
            .limit(10000)
        )
        visits = result.scalars().all()

    date_range = f"{args.date_from}_{args.date_to}"
    output = args.output or f"visites_{date_range}.{args.format}"

    if args.format == "csv":
        buffer = visits_to_csv(visits)
    else:
        buffer = visits_to_excel(visits, date_range)

    with open(output, "wb") as f:
        f.write(buffer.getvalue())

    print(f"Exportades {len(visits)} visites a {output}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
