#!/usr/bin/env python3
"""Crea el document legal complet (Bones Pràctiques + RGPD bàsic) i l'activa.

Combina:
  1. Bones Pràctiques per a Visitants / Subcontractistes (IT04.03), reutilitzades
     d'`import_visitor_rules.py` per evitar duplicació.
  2. Secció RGPD bàsica amb enllaç a la política de privacitat per idioma.
"""
import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.models import LegalDocument  # noqa: E402
from import_visitor_rules import build_rules_html  # noqa: E402


RGPD_CA = """
<h3>Registre d'accessos i visites externes</h3>

<p>Les dades facilitades per les persones visitants seran tractades amb la finalitat de gestionar el control d'accés a les instal·lacions de l'empresa, garantir la seguretat de les persones i instal·lacions, així com mantenir la traçabilitat de les visites.</p>

<p>La base jurídica del tractament és l'interès legítim del responsable del tractament.</p>

<p>Les dades es conservaran durant el termini estrictament necessari per complir aquestes finalitats i no seran cedides a tercers excepte obligació legal.</p>

<h3>INFORMACIÓ BÀSICA SOBRE PROTECCIÓ DE DADES</h3>

<ul>
<li><strong>Responsable:</strong> AGRI-ENERGIA, S.A.</li>
<li><strong>Finalitat:</strong> Gestionar el control d'accessos i garantir la seguretat de les instal·lacions.</li>
<li><strong>Legitimació:</strong> Interès legítim de l'empresa en garantir la seguretat.</li>
<li><strong>Destinataris:</strong> No se cediran dades a tercers excepte obligació legal.</li>
<li><strong>Drets:</strong> Podeu exercir els vostres drets a través de protecciodades@agrienergia.com</li>
</ul>

<p><strong>Més informació:</strong><br>
<a href="https://farineracoromina.com/ca/politica-de-privadesa/" target="_blank" rel="noopener">Veure Política de Privacitat</a></p>
""".strip()

RGPD_ES = """
<h3>Registro de accesos y visitas externas</h3>

<p>Los datos facilitados por las personas visitantes serán tratados con la finalidad de gestionar el control de acceso a las instalaciones de la empresa, garantizar la seguridad de las personas e instalaciones, así como mantener la trazabilidad de las visitas.</p>

<p>La base jurídica del tratamiento es el interés legítimo del responsable del tratamiento.</p>

<p>Los datos se conservarán durante el plazo estrictamente necesario para cumplir estas finalidades y no serán cedidos a terceros salvo obligación legal.</p>

<h3>INFORMACIÓN BÁSICA SOBRE PROTECCIÓN DE DATOS</h3>

<ul>
<li><strong>Responsable:</strong> AGRI-ENERGIA, S.A.</li>
<li><strong>Finalidad:</strong> Gestionar el control de accesos y garantizar la seguridad de las instalaciones.</li>
<li><strong>Legitimación:</strong> Interés legítimo de la empresa en garantizar la seguridad.</li>
<li><strong>Destinatarios:</strong> No se cederán datos a terceros salvo obligación legal.</li>
<li><strong>Derechos:</strong> Puede ejercer sus derechos a través de protecciodades@agrienergia.com</li>
</ul>

<p><strong>Más información:</strong><br>
<a href="https://farineracoromina.com/politica-de-privacidad/" target="_blank" rel="noopener">Ver Política de Privacidad</a></p>
""".strip()

RGPD_FR = """
<h3>Registre des accès et visites externes</h3>

<p>Les données fournies par les visiteurs seront traitées dans le but de gérer le contrôle d'accès aux installations de l'entreprise, de garantir la sécurité des personnes et des installations, ainsi que de maintenir la traçabilité des visites.</p>

<p>La base juridique du traitement est l'intérêt légitime du responsable du traitement.</p>

<p>Les données seront conservées pendant la durée strictement nécessaire à la réalisation de ces finalités et ne seront pas communiquées à des tiers, sauf obligation légale.</p>

<h3>INFORMATION DE BASE SUR LA PROTECTION DES DONNÉES</h3>

<ul>
<li><strong>Responsable :</strong> AGRI-ENERGIA, S.A.</li>
<li><strong>Finalité :</strong> Gérer le contrôle d'accès et garantir la sécurité des installations.</li>
<li><strong>Légitimité :</strong> Intérêt légitime de l'entreprise à garantir la sécurité.</li>
<li><strong>Destinataires :</strong> Aucune donnée ne sera transmise à des tiers, sauf obligation légale.</li>
<li><strong>Droits :</strong> Vous pouvez exercer vos droits via protecciodades@agrienergia.com</li>
</ul>

<p><strong>Plus d'informations :</strong><br>
<a href="https://farineracoromina.com/fr/politique-de-confidentialite/" target="_blank" rel="noopener">Voir Politique de Confidentialité</a></p>
""".strip()

RGPD_EN = """
<h3>External access and visits register</h3>

<p>The data provided by visitors will be processed for the purpose of managing access control to the company's facilities, ensuring the safety of people and installations, and maintaining the traceability of visits.</p>

<p>The legal basis for processing is the legitimate interest of the data controller.</p>

<p>Data will be retained for the period strictly necessary to fulfil these purposes and will not be disclosed to third parties except where required by law.</p>

<h3>BASIC INFORMATION ON DATA PROTECTION</h3>

<ul>
<li><strong>Controller:</strong> AGRI-ENERGIA, S.A.</li>
<li><strong>Purpose:</strong> Manage access control and ensure the safety of the facilities.</li>
<li><strong>Legal basis:</strong> Legitimate interest of the company in ensuring security.</li>
<li><strong>Recipients:</strong> Data will not be shared with third parties except where required by law.</li>
<li><strong>Rights:</strong> You may exercise your rights through protecciodades@agrienergia.com</li>
</ul>

<p><strong>More information:</strong><br>
<a href="https://farineracoromina.com/en/privacy-policy/" target="_blank" rel="noopener">View Privacy Policy</a></p>
""".strip()


def build_full_content(lang: str, rgpd: str) -> str:
    return build_rules_html(lang).strip() + "\n\n" + rgpd


async def main():
    ca = build_full_content("ca", RGPD_CA)
    es = build_full_content("es", RGPD_ES)
    fr = build_full_content("fr", RGPD_FR)
    en = build_full_content("en", RGPD_EN)

    engine = create_async_engine(settings.DATABASE_URL)
    sf = async_sessionmaker(engine, class_=AsyncSession)

    async with sf() as s:
        # Desactivar tots els anteriors
        result = await s.execute(select(LegalDocument))
        for doc in result.scalars():
            doc.active = False

        h = hashlib.sha256((ca + es + fr + en).encode()).hexdigest()
        doc = LegalDocument(
            content_hash=h,
            content_ca=ca, content_es=es, content_fr=fr, content_en=en,
            active=True,
        )
        s.add(doc)
        await s.commit()
        print("Document legal (Bones Pràctiques + RGPD) creat i activat")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
