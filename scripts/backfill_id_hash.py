"""Calcula id_document_hash per a totes les visites existents.

Cal executar-lo una sola vegada després d'aplicar la migració 004. Desxifra
cada DNI amb la clau actual i hi calcula l'HMAC amb el LOOKUP_PEPPER del
.env. Fitxers a la BD que no es puguin desxifrar es marquen com a fallits
(no s'aturen la resta de la feina).

Ús:
    python scripts/backfill_id_hash.py
"""
import asyncio
import sys
from pathlib import Path

# Permetre l'execució des de l'arrel del projecte sense PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.models import Visit  # noqa: E402
from app.services.crypto import decrypt, hash_id_document  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Visit).where(Visit.id_document_hash.is_(None))
        )
        visits = result.scalars().all()
        ok = 0
        fail = 0
        for v in visits:
            try:
                plaintext = decrypt(v.id_document_enc, v.id_document_iv)
                v.id_document_hash = hash_id_document(plaintext)
                ok += 1
            except Exception as exc:
                print(f"FAIL  visit={v.id}  err={exc}")
                fail += 1
        await db.commit()
        print(f"Backfill complet. OK={ok}  FAIL={fail}  TOTAL={len(visits)}")
        return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
