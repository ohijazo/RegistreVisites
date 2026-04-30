"""Importa el text d'IT04.03 (Bones Pràctiques per a Visitants i Subcontractistes)
com a noves "Normes d'accés i seguretat" del document legal.

Combina el text nou (4 idiomes) amb la secció RGPD existent del document
legal actiu — així les noves normes substitueixen les antigues sense perdre
la informació de protecció de dades, que és obligatòria per llei.

El document nou es crea com a **inactiu**. L'admin l'ha d'activar
manualment des de /admin/legal després de revisar-lo.

Ús:
    venv\\Scripts\\python.exe scripts\\import_visitor_rules.py
"""
import asyncio
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.models import LegalDocument  # noqa: E402


# ── Contingut IT04.03 per idioma ─────────────────────────────────────────

IT_TITLE = {
    "ca": "Bones Pràctiques per a Visitants / Subcontractistes",
    "es": "Buenas Prácticas para Visitantes / Subcontratistas",
    "fr": "Bonnes Pratiques pour les Visiteurs et Sous-traitants",
    "en": "Good Practices for Visitors and Subcontractors",
}

IT_GREETING = {
    "ca": "Benvolgut/da visitant / subcontractista, benvingut/da a <strong>FARINERA COROMINA</strong>.",
    "es": "Estimado/a visitante / subcontratista, bienvenido/a a <strong>FARINERA COROMINA</strong>.",
    "fr": "Cher/Chère visiteur(se) / sous-traitant(e), bienvenue chez <strong>FARINERA COROMINA</strong>.",
    "en": "Dear visitor / subcontractor, welcome to <strong>FARINERA COROMINA</strong>.",
}

IT_INTRO = {
    "ca": ("Amb la finalitat de garantir el compliment de les normes de qualitat, "
           "seguretat i higiene implantades a l'empresa, li demanem que durant la "
           "seva visita a les instal·lacions de producció i/o magatzem compleixi "
           "estrictament les següents normes:"),
    "es": ("Con el fin de garantizar el cumplimiento de las normas de calidad, "
           "seguridad e higiene implantadas en la empresa, le rogamos que durante "
           "su visita a las instalaciones de producción y/o almacén observe "
           "estrictamente las siguientes normas:"),
    "fr": ("Afin de garantir le respect des normes de qualité, de sécurité et "
           "d'hygiène mises en place dans l'entreprise, nous vous demandons de "
           "respecter strictement les règles suivantes lors de votre visite des "
           "installations de production et/ou de l'entrepôt :"),
    "en": ("In order to ensure compliance with the quality, safety and hygiene "
           "standards implemented in the company, we kindly ask you to strictly "
           "observe the following rules during your visit to the production "
           "and/or warehouse facilities:"),
}

IT_BULLETS = {
    "ca": [
        "No portar rellotges ni joies (anells, collarets, braçalets o arracades de qualsevol tipus).",
        "Preferiblement, no portar maquillatge ni ungles o pestanyes postisses, pintades o llargues. En cas de no poder evitar-ho, es recomana l'ús de guants durant la visita.",
        "Evitar l'ús excessiu o d'olor intensa de perfum o loció després de l'afaitat.",
        "Rentar-se correctament les mans abans d'accedir a les instal·lacions.",
        "Evitar tossir o esternudar directament sobre els productes. En cas necessari, utilitzar un mocador o cobrir-se adequadament.",
        "Queda prohibit menjar a les zones de magatzem i producció, així com introduir-hi menjar o beguda.",
        "Està prohibit fumar, vapejar o utilitzar qualsevol tipus de tabac a tot el recinte de l'empresa, inclòs el perímetre exterior, excepte a la zona habilitada davant del menjador.",
        "Li preguem que ens informi de qualsevol malaltia infecciosa o trastorn rellevant que pateixi o amb el qual hagi estat en contacte. Si es veiés afectat/da, s'intentarà realitzar la visita quan no presenti símptomes; en cas contrari, haurà de mantenir-se el més allunyat possible del producte.",
        "En accedir a les instal·lacions se li facilitarà la roba de protecció necessària (bata i gorro), d'ús obligatori durant tota la visita.",
        "Serà acompanyat/da en tot moment dins les instal·lacions. Durant la visita, li agraïm que no toqui els productes ni s'hi apropi en excés.",
    ],
    "es": [
        "No llevar relojes ni joyas (anillos, colgantes, pulseras o pendientes de cualquier tipo).",
        "Preferiblemente, no llevar maquillaje ni uñas o pestañas postizas, pintadas o largas. En caso de no poder evitarlo, se recomienda el uso de guantes durante la visita.",
        "Evitar el uso de perfume o loción after shave en exceso o de olor intenso.",
        "Lavarse correctamente las manos antes de acceder a las instalaciones.",
        "Evitar toser o estornudar directamente sobre los productos. En caso necesario, utilizar un pañuelo o cubrirse adecuadamente.",
        "Queda prohibido comer en las zonas de almacén y producción, así como introducir comida o bebida en las mismas.",
        "Está prohibido fumar, vapear o utilizar cualquier tipo de tabaco en todo el recinto de la empresa, incluido el perímetro exterior, excepto en la zona habilitada frente al comedor.",
        "Rogamos nos informe de cualquier enfermedad infecciosa o trastorno relevante que padezca o con el que haya estado en contacto. En caso de verse afectado/a, se intentará realizar la visita cuando no presente síntomas; de no ser posible, deberá mantenerse lo más alejado posible del producto.",
        "A su acceso a las instalaciones se le facilitará la ropa de protección necesaria (bata y gorro), de uso obligatorio durante toda la visita.",
        "Será acompañado/a en todo momento dentro de las instalaciones. Durante la visita, le agradecemos que no toque los productos ni se acerque en exceso a los mismos.",
    ],
    "fr": [
        "Ne pas porter de montres ni de bijoux (bagues, colliers, bracelets ou boucles d'oreilles de quelque type que ce soit).",
        "De préférence, ne pas porter de maquillage ni d'ongles ou de cils artificiels, peints ou longs. Si cela ne peut être évité, l'utilisation de gants pendant la visite est recommandée.",
        "Éviter l'utilisation excessive de parfum ou d'après-rasage à l'odeur forte.",
        "Se laver correctement les mains avant d'accéder aux installations.",
        "Éviter de tousser ou d'éternuer directement sur les produits. Le cas échéant, utiliser un mouchoir ou se couvrir correctement.",
        "Il est interdit de manger dans les zones de production et d'entrepôt, ainsi que d'y introduire de la nourriture ou des boissons.",
        "Il est interdit de fumer, vapoter ou utiliser tout autre type de tabac dans l'ensemble de l'enceinte de l'entreprise, y compris le périmètre extérieur, sauf dans la zone autorisée située devant le réfectoire.",
        "Nous vous prions de nous informer de toute maladie infectieuse ou affection pertinente dont vous souffrez ou avec laquelle vous avez été en contact. En cas de symptômes, la visite sera organisée à un autre moment ; si cela n'est pas possible, vous devrez rester le plus éloigné possible des produits.",
        "À votre entrée dans les installations, les équipements de protection nécessaires (blouse et charlotte) vous seront fournis et devront être portés pendant toute la durée de la visite.",
        "Vous serez accompagné(e) à tout moment à l'intérieur des installations. Durant la visite, merci de ne pas toucher les produits ni de vous en approcher excessivement.",
    ],
    "en": [
        "Do not wear watches or jewellery (rings, necklaces, bracelets or earrings of any kind).",
        "Preferably, do not wear make-up or artificial, painted or long nails or eyelashes. If this cannot be avoided, the use of gloves during the visit is recommended.",
        "Avoid excessive use of perfume or strongly scented aftershave.",
        "Wash your hands properly before entering the facilities.",
        "Avoid coughing or sneezing directly over the products. If necessary, use a tissue or cover yourself appropriately.",
        "Eating in production and warehouse areas is prohibited, as well as bringing food or beverages into these areas.",
        "Smoking, vaping or using any type of tobacco is prohibited throughout the company premises, including the outdoor perimeter, except in the designated area in front of the canteen.",
        "Please inform us of any infectious disease or relevant condition that you may have or have been in contact with. If affected, the visit will be arranged when no symptoms are present; if this is not possible, you must keep as far away from the product as possible.",
        "Upon entering the facilities, the required protective clothing (gown and hair cover) will be provided and must be worn throughout the visit.",
        "You will be accompanied at all times within the facilities. During the visit, please do not touch the products or get unnecessarily close to them.",
    ],
}

IT_THANKS = {
    "ca": "Li agraïm la seva comprensió i col·laboració.",
    "es": "Le agradecemos su comprensión y colaboración.",
    "fr": "Nous vous remercions de votre compréhension et de votre collaboration.",
    "en": "Thank you for your understanding and cooperation.",
}


# ── Helpers ─────────────────────────────────────────────────────────────

# Marcadors per trobar l'inici de la secció RGPD a cada idioma
RGPD_MARKERS_RE = re.compile(
    r"<h3[^>]*>\s*("
    r"INFORMACIÓ SOBRE PROTECCIÓ"          # ca
    r"|INFORMACIÓN SOBRE PROTECCIÓN"       # es
    r"|INFORMATIONS? SUR LA PROTECTION"    # fr
    r"|PERSONAL DATA PROTECTION"           # en
    r")",
    re.IGNORECASE,
)


def extract_rgpd_section(html: str) -> str:
    """Retorna la secció RGPD (des del primer <h3> que conté el marcador
    fins al final de la cadena). Si no troba el marcador, retorna ''."""
    m = RGPD_MARKERS_RE.search(html)
    if not m:
        return ""
    return html[m.start():]


def build_rules_html(lang: str) -> str:
    """Construeix la secció de Bones Pràctiques en HTML."""
    bullets_html = "\n".join(f"<li>{b}</li>" for b in IT_BULLETS[lang])
    return (
        f"<h3>{IT_TITLE[lang]}</h3>\n"
        f"<p>{IT_GREETING[lang]}</p>\n"
        f"<p>{IT_INTRO[lang]}</p>\n"
        f"<ul>\n{bullets_html}\n</ul>\n"
        f"<p>{IT_THANKS[lang]}</p>\n"
    )


# ── Main ────────────────────────────────────────────────────────────────

async def main() -> int:
    async with AsyncSessionLocal() as db:
        # Document actiu actual (per extreure'n la secció RGPD)
        result = await db.execute(
            select(LegalDocument).where(LegalDocument.active.is_(True))
        )
        current = result.scalar_one_or_none()
        if not current:
            print("ERROR: no hi ha cap document legal actiu actualment.")
            print("Cal que existeixi un per poder-ne preservar la part RGPD.")
            return 1

        new_contents: dict[str, str] = {}
        for lang in ("ca", "es", "fr", "en"):
            current_html = getattr(current, f"content_{lang}") or ""
            rgpd = extract_rgpd_section(current_html)
            if not rgpd:
                print(f"AVÍS [{lang}]: no s'ha trobat la secció RGPD; s'usarà el text complet de l'idioma.")
                rgpd = current_html  # fallback
            new_contents[lang] = build_rules_html(lang) + "\n" + rgpd

        content_hash = hashlib.sha256(
            (new_contents["ca"] + new_contents["es"]
             + new_contents["fr"] + new_contents["en"]).encode()
        ).hexdigest()

        # Si ja existeix un doc amb el mateix hash, no en creem un altre
        existing = await db.execute(
            select(LegalDocument).where(LegalDocument.content_hash == content_hash)
        )
        if existing.scalar_one_or_none():
            print(f"Ja existeix un document amb hash {content_hash[:12]}... res a fer.")
            return 0

        new_doc = LegalDocument(
            content_hash=content_hash,
            content_ca=new_contents["ca"],
            content_es=new_contents["es"],
            content_fr=new_contents["fr"],
            content_en=new_contents["en"],
            active=False,  # ⚠ Inactiu — l'admin l'ha d'activar a /admin/legal
        )
        db.add(new_doc)
        await db.commit()
        # Output ASCII-only per evitar UnicodeEncodeError a consoles cp1252
        print("[OK] Document legal creat (inactiu).")
        print(f"  ID:   {new_doc.id}")
        print(f"  Hash: {content_hash[:12]}...")
        print()
        print("Per activar-lo:")
        print("  1. Ves a /admin/legal")
        print(f"  2. Clica 'Activar' a la fila del document {new_doc.id}")
        print("  3. (Opcional) Revisa el contingut abans d'activar")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
