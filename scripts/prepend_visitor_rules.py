"""Prefixa el contingut de l'IT04.03 (Bones Pràctiques per a Visitants i
Subcontractistes) al document legal actiu, en els 4 idiomes, conservant
íntegrament el text existent (NORMES D'ACCÉS + RGPD).

Crea un document nou **inactiu**: l'admin l'ha d'activar manualment des
de /admin/legal després de revisar-lo.

Ús:
    venv\\Scripts\\python.exe scripts\\prepend_visitor_rules.py
"""
import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.models import LegalDocument  # noqa: E402
from import_visitor_rules import build_rules_html  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LegalDocument).where(LegalDocument.active.is_(True))
        )
        current = result.scalar_one_or_none()
        if not current:
            print("ERROR: no hi ha cap document legal actiu actualment.")
            return 1

        new_contents: dict[str, str] = {}
        for lang in ("ca", "es", "fr", "en"):
            existing = getattr(current, f"content_{lang}") or ""
            new_contents[lang] = build_rules_html(lang).strip() + "\n\n" + existing

        content_hash = hashlib.sha256(
            (new_contents["ca"] + new_contents["es"]
             + new_contents["fr"] + new_contents["en"]).encode()
        ).hexdigest()

        existing_doc = await db.execute(
            select(LegalDocument).where(LegalDocument.content_hash == content_hash)
        )
        if existing_doc.scalar_one_or_none():
            print(f"Ja existeix un document amb hash {content_hash[:12]}... res a fer.")
            return 0

        new_doc = LegalDocument(
            content_hash=content_hash,
            content_ca=new_contents["ca"],
            content_es=new_contents["es"],
            content_fr=new_contents["fr"],
            content_en=new_contents["en"],
            active=False,
        )
        db.add(new_doc)
        await db.commit()
        print("[OK] Document legal creat (inactiu).")
        print(f"  ID:   {new_doc.id}")
        print(f"  Hash: {content_hash[:12]}...")
        print()
        print("Per activar-lo:")
        print("  1. Ves a /admin/legal")
        print(f"  2. Clica 'Activar' a la fila del document {new_doc.id}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
