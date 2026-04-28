"""Tanca automàticament les visites obertes que superen el llindar configurat.

Pensat per executar-se cada nit via cron. Marca les visites amb
checkout_method='auto_eod' i deixa rastre a audit_logs perquè
l'historial conservi la diferència respecte d'un checkout normal.

Ús (manual o cron):
    python scripts/auto_close_visits.py
    # Configurable: AUTO_CLOSE_AFTER_HOURS al .env (per defecte 12 h)

Cron suggerit (a /etc/cron.d/visites o crontab de www-data):
    55 23 * * * /opt/visites/venv/bin/python /opt/visites/scripts/auto_close_visits.py >> /var/log/visites/auto_close.log 2>&1
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Permetre l'execució des de l'arrel del projecte sense PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.models import AuditLog, Visit  # noqa: E402


async def main() -> int:
    threshold = datetime.now(timezone.utc) - timedelta(hours=settings.AUTO_CLOSE_AFTER_HOURS)
    closed = 0
    failed = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Visit).where(
                Visit.checked_out_at.is_(None),
                Visit.checked_in_at < threshold,
            )
        )
        visits = result.scalars().all()

        for v in visits:
            try:
                v.checked_out_at = datetime.now(timezone.utc)
                v.checkout_method = "auto_eod"
                db.add(AuditLog(
                    admin_id=None,
                    visit_id=v.id,
                    action="auto_checkout",
                    ip_address=None,
                    detail=json.dumps({
                        "reason": "auto_eod",
                        "threshold_hours": settings.AUTO_CLOSE_AFTER_HOURS,
                        "checked_in_at": v.checked_in_at.isoformat(),
                    }),
                ))
                closed += 1
            except Exception as exc:
                failed += 1
                print(f"FAIL  visit={v.id}  err={exc}")

        await db.commit()

    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] auto_close_visits: closed={closed} failed={failed} threshold={settings.AUTO_CLOSE_AFTER_HOURS}h")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
