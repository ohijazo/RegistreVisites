#!/usr/bin/env python3
"""Crea un document legal complet i conforme RGPD + LOPDGDD per a registre de visites."""
import asyncio
import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import LegalDocument

CONTENT_CA = """
<h3>NORMES D'ACCÉS I SEGURETAT DE LES INSTAL·LACIONS</h3>

<p>En accedir a les instal·lacions de <strong>{company_name}</strong>, el visitant es compromet a:</p>

<ol>
<li>Portar visible la identificació de visitant durant tota l'estada.</li>
<li>No accedir a zones restringides sense acompanyament del personal autoritzat.</li>
<li>Seguir en tot moment les indicacions del personal de seguretat i del personal de l'empresa.</li>
<li>En cas d'emergència, seguir les rutes d'evacuació senyalitzades i les instruccions del personal.</li>
<li>No introduir materials perillosos, armes o substàncies prohibides a les instal·lacions.</li>
<li>No fer fotografies ni enregistraments de vídeo sense autorització prèvia.</li>
<li>Respectar les normes de seguretat i salut laboral vigents a les instal·lacions.</li>
</ol>

<h3>INFORMACIÓ SOBRE PROTECCIÓ DE DADES PERSONALS</h3>

<p><strong>Responsable del tractament:</strong><br>
{company_name}<br>
{company_address}<br>
Correu electrònic del DPD: {company_email}</p>

<p><strong>Finalitat del tractament:</strong><br>
Les dades personals recollides en aquest registre seran tractades amb les següents finalitats:</p>
<ul>
<li>Gestió i control d'accés a les instal·lacions per garantir la seguretat de les persones i els béns.</li>
<li>Compliment de les obligacions legals en matèria de seguretat i prevenció de riscos laborals.</li>
<li>Gestió administrativa de les visites (coordinació amb els departaments visitats).</li>
</ul>

<p><strong>Base jurídica del tractament:</strong><br>
El tractament de les vostres dades es basa en:</p>
<ul>
<li><strong>Interès legítim</strong> (article 6.1.f del RGPD): garantir la seguretat de les persones, instal·lacions i béns de l'empresa.</li>
<li><strong>Obligació legal</strong> (article 6.1.c del RGPD): compliment de la normativa de seguretat privada (Llei 5/2014) i prevenció de riscos laborals (Llei 31/1995).</li>
</ul>

<p><strong>Dades recollides:</strong><br>
Nom i cognoms, empresa/organització, document d'identitat (emmagatzemat de forma xifrada), departament visitat, motiu de la visita, telèfon de contacte (opcional), hora d'entrada i sortida, signatura, adreça IP i agent d'usuari.</p>

<p><strong>Termini de conservació:</strong><br>
Les dades es conservaran durant un termini màxim de <strong>2 anys</strong> des de la data de la visita. Transcorregut aquest termini, les dades seran eliminades de forma segura.</p>

<p><strong>Destinataris:</strong><br>
Les dades no seran cedides a tercers, excepte per obligació legal (forces i cossos de seguretat, autoritats judicials) o per a la gestió de la seguretat de les instal·lacions.</p>

<p><strong>Drets de les persones interessades:</strong><br>
Podeu exercir els vostres drets d'accés, rectificació, supressió, limitació del tractament, portabilitat i oposició enviant un correu electrònic a <strong>{company_email}</strong>, adjuntant còpia del vostre document d'identitat.</p>

<p>Així mateix, teniu dret a presentar una reclamació davant l'<strong>Agència Espanyola de Protecció de Dades</strong> (AEPD) — <em>www.aepd.es</em> — o davant l'<strong>Autoritat Catalana de Protecció de Dades</strong> (APDCAT) — <em>www.apdcat.gencat.cat</em>.</p>

<p><strong>Caràcter obligatori de les dades:</strong><br>
La provisió de les dades marcades com a obligatòries és necessària per a permetre l'accés a les instal·lacions. La negativa a facilitar-les implicarà la impossibilitat d'accedir-hi.</p>
""".strip()

CONTENT_ES = """
<h3>NORMAS DE ACCESO Y SEGURIDAD DE LAS INSTALACIONES</h3>

<p>Al acceder a las instalaciones de <strong>{company_name}</strong>, el visitante se compromete a:</p>

<ol>
<li>Llevar visible la identificación de visitante durante toda la estancia.</li>
<li>No acceder a zonas restringidas sin acompañamiento del personal autorizado.</li>
<li>Seguir en todo momento las indicaciones del personal de seguridad y del personal de la empresa.</li>
<li>En caso de emergencia, seguir las rutas de evacuación señalizadas y las instrucciones del personal.</li>
<li>No introducir materiales peligrosos, armas o sustancias prohibidas en las instalaciones.</li>
<li>No realizar fotografías ni grabaciones de vídeo sin autorización previa.</li>
<li>Respetar las normas de seguridad y salud laboral vigentes en las instalaciones.</li>
</ol>

<h3>INFORMACIÓN SOBRE PROTECCIÓN DE DATOS PERSONALES</h3>

<p><strong>Responsable del tratamiento:</strong><br>
{company_name}<br>
{company_address}<br>
Correo electrónico del DPD: {company_email}</p>

<p><strong>Finalidad del tratamiento:</strong><br>
Los datos personales recogidos en este registro serán tratados con las siguientes finalidades:</p>
<ul>
<li>Gestión y control de acceso a las instalaciones para garantizar la seguridad de las personas y los bienes.</li>
<li>Cumplimiento de las obligaciones legales en materia de seguridad y prevención de riesgos laborales.</li>
<li>Gestión administrativa de las visitas (coordinación con los departamentos visitados).</li>
</ul>

<p><strong>Base jurídica del tratamiento:</strong><br>
El tratamiento de sus datos se basa en:</p>
<ul>
<li><strong>Interés legítimo</strong> (artículo 6.1.f del RGPD): garantizar la seguridad de las personas, instalaciones y bienes de la empresa.</li>
<li><strong>Obligación legal</strong> (artículo 6.1.c del RGPD): cumplimiento de la normativa de seguridad privada (Ley 5/2014) y prevención de riesgos laborales (Ley 31/1995).</li>
</ul>

<p><strong>Datos recogidos:</strong><br>
Nombre y apellidos, empresa/organización, documento de identidad (almacenado de forma cifrada), departamento visitado, motivo de la visita, teléfono de contacto (opcional), hora de entrada y salida, firma, dirección IP y agente de usuario.</p>

<p><strong>Plazo de conservación:</strong><br>
Los datos se conservarán durante un plazo máximo de <strong>2 años</strong> desde la fecha de la visita. Transcurrido este plazo, los datos serán eliminados de forma segura.</p>

<p><strong>Destinatarios:</strong><br>
Los datos no serán cedidos a terceros, salvo por obligación legal (fuerzas y cuerpos de seguridad, autoridades judiciales) o para la gestión de la seguridad de las instalaciones.</p>

<p><strong>Derechos de las personas interesadas:</strong><br>
Puede ejercer sus derechos de acceso, rectificación, supresión, limitación del tratamiento, portabilidad y oposición enviando un correo electrónico a <strong>{company_email}</strong>, adjuntando copia de su documento de identidad.</p>

<p>Asimismo, tiene derecho a presentar una reclamación ante la <strong>Agencia Española de Protección de Datos</strong> (AEPD) — <em>www.aepd.es</em> — o ante la <strong>Autoritat Catalana de Protecció de Dades</strong> (APDCAT) — <em>www.apdcat.gencat.cat</em>.</p>

<p><strong>Carácter obligatorio de los datos:</strong><br>
La provisión de los datos marcados como obligatorios es necesaria para permitir el acceso a las instalaciones. La negativa a facilitarlos implicará la imposibilidad de acceder a las mismas.</p>
""".strip()

CONTENT_FR = """
<h3>RÈGLES D'ACCÈS ET DE SÉCURITÉ DES INSTALLATIONS</h3>

<p>En accédant aux installations de <strong>{company_name}</strong>, le visiteur s'engage à :</p>

<ol>
<li>Porter l'identification de visiteur de manière visible pendant toute la durée du séjour.</li>
<li>Ne pas accéder aux zones restreintes sans être accompagné par le personnel autorisé.</li>
<li>Suivre à tout moment les instructions du personnel de sécurité et du personnel de l'entreprise.</li>
<li>En cas d'urgence, suivre les itinéraires d'évacuation signalés et les instructions du personnel.</li>
<li>Ne pas introduire de matériaux dangereux, d'armes ou de substances interdites dans les installations.</li>
<li>Ne pas prendre de photographies ni réaliser d'enregistrements vidéo sans autorisation préalable.</li>
<li>Respecter les normes de sécurité et de santé au travail en vigueur dans les installations.</li>
</ol>

<h3>INFORMATION SUR LA PROTECTION DES DONNÉES PERSONNELLES</h3>

<p><strong>Responsable du traitement :</strong><br>
{company_name}<br>
{company_address}<br>
E-mail du DPD : {company_email}</p>

<p><strong>Finalité du traitement :</strong><br>
Les données personnelles collectées dans ce registre seront traitées aux fins suivantes :</p>
<ul>
<li>Gestion et contrôle de l'accès aux installations pour garantir la sécurité des personnes et des biens.</li>
<li>Respect des obligations légales en matière de sécurité et de prévention des risques professionnels.</li>
<li>Gestion administrative des visites (coordination avec les départements visités).</li>
</ul>

<p><strong>Base juridique du traitement :</strong><br>
Le traitement de vos données repose sur :</p>
<ul>
<li><strong>L'intérêt légitime</strong> (article 6.1.f du RGPD) : garantir la sécurité des personnes, des installations et des biens de l'entreprise.</li>
<li><strong>L'obligation légale</strong> (article 6.1.c du RGPD) : respect de la réglementation en matière de sécurité.</li>
</ul>

<p><strong>Données collectées :</strong><br>
Nom et prénoms, entreprise/organisation, document d'identité (stocké de manière chiffrée), département visité, motif de la visite, téléphone (facultatif), heure d'entrée et de sortie, signature, adresse IP et agent utilisateur.</p>

<p><strong>Durée de conservation :</strong><br>
Les données seront conservées pendant une durée maximale de <strong>2 ans</strong> à compter de la date de la visite. Passé ce délai, les données seront supprimées de manière sécurisée.</p>

<p><strong>Destinataires :</strong><br>
Les données ne seront pas communiquées à des tiers, sauf obligation légale.</p>

<p><strong>Droits des personnes concernées :</strong><br>
Vous pouvez exercer vos droits d'accès, de rectification, d'effacement, de limitation, de portabilité et d'opposition en envoyant un e-mail à <strong>{company_email}</strong>, accompagné d'une copie de votre pièce d'identité.</p>

<p>Vous avez également le droit de déposer une réclamation auprès de l'<strong>Agencia Española de Protección de Datos</strong> (AEPD) — <em>www.aepd.es</em>.</p>

<p><strong>Caractère obligatoire des données :</strong><br>
La fourniture des données marquées comme obligatoires est nécessaire pour permettre l'accès aux installations. Le refus de les fournir entraînera l'impossibilité d'y accéder.</p>
""".strip()

CONTENT_EN = """
<h3>FACILITY ACCESS AND SECURITY RULES</h3>

<p>By accessing the facilities of <strong>{company_name}</strong>, the visitor agrees to:</p>

<ol>
<li>Wear the visitor identification visibly at all times during the visit.</li>
<li>Not access restricted areas without being accompanied by authorised personnel.</li>
<li>Follow the instructions of security and company personnel at all times.</li>
<li>In case of emergency, follow the marked evacuation routes and staff instructions.</li>
<li>Not bring dangerous materials, weapons or prohibited substances into the facilities.</li>
<li>Not take photographs or video recordings without prior authorisation.</li>
<li>Comply with the occupational health and safety regulations in force at the facilities.</li>
</ol>

<h3>PERSONAL DATA PROTECTION INFORMATION</h3>

<p><strong>Data controller:</strong><br>
{company_name}<br>
{company_address}<br>
DPO e-mail: {company_email}</p>

<p><strong>Purpose of processing:</strong><br>
The personal data collected in this register will be processed for the following purposes:</p>
<ul>
<li>Management and control of access to the facilities to ensure the safety of people and property.</li>
<li>Compliance with legal obligations regarding security and occupational risk prevention.</li>
<li>Administrative management of visits (coordination with the departments visited).</li>
</ul>

<p><strong>Legal basis for processing:</strong><br>
The processing of your data is based on:</p>
<ul>
<li><strong>Legitimate interest</strong> (Article 6.1.f GDPR): ensuring the safety of people, facilities and company property.</li>
<li><strong>Legal obligation</strong> (Article 6.1.c GDPR): compliance with security and occupational risk prevention regulations.</li>
</ul>

<p><strong>Data collected:</strong><br>
First and last name, company/organisation, identity document (stored in encrypted form), department visited, reason for visit, contact telephone (optional), entry and exit time, signature, IP address and user agent.</p>

<p><strong>Retention period:</strong><br>
Data will be retained for a maximum period of <strong>2 years</strong> from the date of the visit. After this period, data will be securely deleted.</p>

<p><strong>Recipients:</strong><br>
Data will not be disclosed to third parties, except where required by law (law enforcement, judicial authorities) or for facility security management.</p>

<p><strong>Data subject rights:</strong><br>
You may exercise your rights of access, rectification, erasure, restriction, portability and objection by sending an e-mail to <strong>{company_email}</strong>, enclosing a copy of your identity document.</p>

<p>You also have the right to lodge a complaint with the <strong>Spanish Data Protection Agency</strong> (AEPD) — <em>www.aepd.es</em> — or the <strong>Catalan Data Protection Authority</strong> (APDCAT) — <em>www.apdcat.gencat.cat</em>.</p>

<p><strong>Mandatory nature of data:</strong><br>
Provision of data marked as mandatory is necessary to allow access to the facilities. Refusal to provide such data will result in the inability to access the premises.</p>
""".strip()


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    sf = async_sessionmaker(engine, class_=AsyncSession)

    # Substituir les variables
    replacements = {
        "{company_name}": settings.COMPANY_NAME,
        "{company_address}": settings.COMPANY_ADDRESS or "—",
        "{company_email}": settings.COMPANY_EMAIL,
    }

    ca = CONTENT_CA
    es = CONTENT_ES
    fr = CONTENT_FR
    en = CONTENT_EN
    for key, val in replacements.items():
        ca = ca.replace(key, val)
        es = es.replace(key, val)
        fr = fr.replace(key, val)
        en = en.replace(key, val)

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
        print("Document legal RGPD complet creat i activat")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
