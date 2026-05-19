"""Contingut multilingüe de la Notificació de Riscos / Mesures Preventives.

Aquesta informació prové del document
`docs/Notificació de riscus, mesures preventives.docx` (original en castellà)
i es fa servir en dos llocs:

- L'script `scripts/prepend_risk_notification.py`, que prefixa el text
  al document legal actiu.
- La ruta `/{lang}/risk-notification`, que mostra els pictogrames amb
  el text corresponent per a consulta del visitant durant la lectura
  del consentiment.

Les imatges es troben a `static/docs/riscos/imageN.png` (de 1 a 12) i
segueixen l'ordre original del docx.
"""
COMPANY_HEADER = "Farinera Coromina"

PAGE_TITLE = {
    "ca": "Notificació de Riscos / Mesures preventives",
    "es": "Notificación de Riesgos / Medidas preventivas",
    "fr": "Notification des Risques / Mesures préventives",
    "en": "Risk Notification / Preventive Measures",
}

SECTION_RISKS = {
    "ca": "RISCOS PRINCIPALS",
    "es": "RIESGOS PRINCIPALES",
    "fr": "RISQUES PRINCIPAUX",
    "en": "MAIN RISKS",
}

SECTION_MEASURES = {
    "ca": "MESURES PREVENTIVES",
    "es": "MEDIDAS PREVENTIVAS",
    "fr": "MESURES PRÉVENTIVES",
    "en": "PREVENTIVE MEASURES",
}

SECTION_EMERGENCY = {
    "ca": "EN CAS D'EMERGÈNCIA",
    "es": "EN CASO DE EMERGENCIA",
    "fr": "EN CAS D'URGENCE",
    "en": "IN CASE OF EMERGENCY",
}

# Cada element: (imatge, text per idioma). L'ordre segueix el docx.
RISKS = [
    {
        "image": "image1.png",
        "text": {
            "ca": "<strong>Risc d'explosió per pols:</strong> ambient amb pols en suspensió. Prohibit fumar o generar espurnes.",
            "es": "<strong>Riesgo de explosión por polvo:</strong> ambiente con polvo en suspensión. Prohibido fumar o generar chispas.",
            "fr": "<strong>Risque d'explosion par poussière :</strong> environnement contenant de la poussière en suspension. Il est interdit de fumer ou de provoquer des étincelles.",
            "en": "<strong>Dust explosion hazard:</strong> environment with airborne dust. Smoking or generating sparks is forbidden.",
        },
    },
    {
        "image": "image2.png",
        "text": {
            "ca": "<strong>Maquinària en moviment:</strong> no tocar els equips i mantenir distància.",
            "es": "<strong>Maquinaria en movimiento:</strong> no tocar los equipos y mantener distancia.",
            "fr": "<strong>Machines en mouvement :</strong> ne pas toucher les équipements et garder ses distances.",
            "en": "<strong>Moving machinery:</strong> do not touch equipment and keep a safe distance.",
        },
    },
    {
        "image": "image3.png",
        "text": {
            "ca": "<strong>Trànsit intern:</strong> presència de carretons elevadors i camions. Atenció i respecte de les zones de maniobra.",
            "es": "<strong>Tráfico interno:</strong> presencia de carretillas y camiones. Atención y respeto de las zonas de maniobra.",
            "fr": "<strong>Trafic interne :</strong> présence de chariots élévateurs et de camions. Soyez attentif et respectez les zones de manœuvre.",
            "en": "<strong>Internal traffic:</strong> presence of forklifts and trucks. Stay alert and respect manoeuvring areas.",
        },
    },
    {
        "image": "image4.png",
        "text": {
            "ca": "<strong>Exposició a la pols:</strong> pot causar irritació. Seguiu les indicacions del personal.",
            "es": "<strong>Exposición al polvo:</strong> puede causar irritación. Siga las indicaciones del personal.",
            "fr": "<strong>Exposition à la poussière :</strong> peut causer des irritations. Suivez les indications du personnel.",
            "en": "<strong>Dust exposure:</strong> may cause irritation. Follow staff instructions.",
        },
    },
    {
        "image": "image5.png",
        "text": {
            "ca": "<strong>Risc d'incendi:</strong> respecteu la senyalització i les normes de seguretat.",
            "es": "<strong>Riesgo de incendio:</strong> respete la señalización y las normas de seguridad.",
            "fr": "<strong>Risque d'incendie :</strong> respectez la signalisation et les règles de sécurité.",
            "en": "<strong>Fire hazard:</strong> respect signage and safety rules.",
        },
    },
    {
        "image": "image6.png",
        "text": {
            "ca": "<strong>Risc de soroll.</strong>",
            "es": "<strong>Riesgo de ruido.</strong>",
            "fr": "<strong>Risque de bruit.</strong>",
            "en": "<strong>Noise hazard.</strong>",
        },
    },
]

MEASURES = [
    {
        "image": "image7.png",
        "text": {
            "ca": "Mantingueu sempre una distància de seguretat respecte a maquinària i vehicles.",
            "es": "Mantenga siempre una distancia de seguridad respecto a maquinaria y vehículos.",
            "fr": "Maintenez toujours une distance de sécurité par rapport aux machines et aux véhicules.",
            "en": "Always keep a safe distance from machinery and vehicles.",
        },
    },
    {
        "image": "image8.png",
        "text": {
            "ca": "Circuleu únicament per les zones habilitades per a visitants.",
            "es": "Circule únicamente por las zonas habilitadas para visitantes.",
            "fr": "Circulez uniquement dans les zones autorisées aux visiteurs.",
            "en": "Only walk in the areas authorised for visitors.",
        },
    },
    {
        "image": "image9.png",
        "text": {
            "ca": "No manipuleu equips, instal·lacions ni productes.",
            "es": "No manipule equipos, instalaciones ni productos.",
            "fr": "Ne manipulez ni les équipements, ni les installations, ni les produits.",
            "en": "Do not handle equipment, installations or products.",
        },
    },
    {
        "image": "image10.png",
        "text": {
            "ca": "Eviteu generar pols o accions que puguin provocar espurnes.",
            "es": "Evite generar polvo o acciones que puedan provocar chispas.",
            "fr": "Évitez de générer de la poussière ou des actions susceptibles de provoquer des étincelles.",
            "en": "Avoid generating dust or actions that could cause sparks.",
        },
    },
    {
        "image": "image11.png",
        "text": {
            "ca": "Seguiu en tot moment les indicacions del personal acompanyant.",
            "es": "Siga en todo momento las indicaciones del personal acompañante.",
            "fr": "Suivez à tout moment les indications du personnel accompagnant.",
            "en": "Follow the instructions of the accompanying staff at all times.",
        },
    },
    {
        "image": None,
        "text": {
            "ca": "Utilitzeu els equips de protecció proporcionats.",
            "es": "Utilice los equipos de protección proporcionados.",
            "fr": "Utilisez les équipements de protection qui vous seront fournis.",
            "en": "Use the personal protective equipment provided.",
        },
    },
    {
        "image": None,
        "text": {
            "ca": "Romangueu acompanyat/da durant tota la visita.",
            "es": "Permanezca acompañado/a durante toda la visita.",
            "fr": "Restez accompagné(e) durant toute la visite.",
            "en": "Remain accompanied throughout the visit.",
        },
    },
    {
        "image": None,
        "text": {
            "ca": "Notifiqueu al personal qualsevol situació de risc o incident.",
            "es": "Notifique al personal cualquier situación de riesgo o incidente.",
            "fr": "Signalez au personnel toute situation à risque ou tout incident.",
            "en": "Report any risk situation or incident to staff.",
        },
    },
]

EMERGENCY = [
    {
        "image": "image11.png",
        "text": {
            "ca": "Seguiu les instruccions del personal.",
            "es": "Siga las instrucciones del personal.",
            "fr": "Suivez les instructions du personnel.",
            "en": "Follow staff instructions.",
        },
    },
    {
        "image": "image12.png",
        "text": {
            "ca": "Dirigiu-vos al punt de reunió.",
            "es": "Diríjase al punto de reunión.",
            "fr": "Rendez-vous au point de rassemblement.",
            "en": "Go to the assembly point.",
        },
    },
    {
        "image": None,
        "text": {
            "ca": "Mantingueu la calma.",
            "es": "Mantenga la calma.",
            "fr": "Gardez votre calme.",
            "en": "Stay calm.",
        },
    },
]

# Informació prèvia al consentiment d'imatge/veu (mostrada al doc legal)
IMAGE_USE_TITLE = {
    "ca": "Ús d'imatge i veu",
    "es": "Uso de imagen y voz",
    "fr": "Utilisation de l'image et de la voix",
    "en": "Use of image and voice",
}

IMAGE_USE_INFO = {
    "ca": ("Durant la visita o activitat es podran fer fotografies i/o "
           "enregistraments audiovisuals amb finalitats corporatives i de "
           "comunicació d'<strong>AGRI-ENERGIA, S.A.</strong>, incloent-hi "
           "la seva possible publicació al lloc web corporatiu, xarxes "
           "socials i materials informatius o promocionals. Al final del "
           "document trobareu una casella opcional per autoritzar aquest "
           "ús."),
    "es": ("Durante la visita o actividad podrán realizarse fotografías "
           "y/o grabaciones audiovisuales con fines corporativos y de "
           "comunicación de <strong>AGRI-ENERGIA, S.A.</strong>, "
           "incluyendo su posible publicación en la página web "
           "corporativa, redes sociales y materiales informativos o "
           "promocionales. Al final del documento encontrará una casilla "
           "opcional para autorizar este uso."),
    "fr": ("Pendant la visite ou l'activité, des photographies et/ou des "
           "enregistrements audiovisuels pourront être réalisés à des "
           "fins corporatives et de communication d'"
           "<strong>AGRI-ENERGIA, S.A.</strong>, y compris leur "
           "publication éventuelle sur le site web institutionnel, les "
           "réseaux sociaux et les supports d'information ou "
           "promotionnels. À la fin du document, vous trouverez une case "
           "facultative pour autoriser cet usage."),
    "en": ("During the visit or activity, photographs and/or audiovisual "
           "recordings may be taken for the corporate and communication "
           "purposes of <strong>AGRI-ENERGIA, S.A.</strong>, including "
           "their possible publication on the corporate website, social "
           "media and informational or promotional materials. At the end "
           "of the document you will find an optional checkbox to "
           "authorise this use."),
}


def build_legal_doc_html(lang: str, view_url: str) -> str:
    """Construeix la secció HTML que s'afegeix al document legal.

    `view_url` és l'enllaç a la pàgina amb pictogrames; queda incrustat
    al final del bloc perquè el visitant pugui consultar les imatges
    sense haver de buscar-les."""
    risks = "\n".join(f"<li>{r['text'][lang]}</li>" for r in RISKS)
    measures = "\n".join(f"<li>{m['text'][lang]}</li>" for m in MEASURES)
    emergency = "\n".join(f"<li>{e['text'][lang]}</li>" for e in EMERGENCY)
    link_text = {
        "ca": "Veure pictogrames de la notificació de riscos",
        "es": "Ver pictogramas de la notificación de riesgos",
        "fr": "Voir les pictogrammes de la notification des risques",
        "en": "View the risk notification pictograms",
    }[lang]
    return (
        f"<h3>{PAGE_TITLE[lang]}</h3>\n"
        f"<p><em>{COMPANY_HEADER}</em></p>\n"
        f"<p><strong>{SECTION_RISKS[lang]}</strong></p>\n"
        f"<ul>\n{risks}\n</ul>\n"
        f"<p><strong>{SECTION_MEASURES[lang]}</strong></p>\n"
        f"<ul>\n{measures}\n</ul>\n"
        f"<p><strong>{SECTION_EMERGENCY[lang]}</strong></p>\n"
        f"<ul>\n{emergency}\n</ul>\n"
        f"<p><a href=\"{view_url}\" target=\"_blank\" rel=\"noopener\">"
        f"{link_text} ↗</a></p>\n"
        f"<h3>{IMAGE_USE_TITLE[lang]}</h3>\n"
        f"<p>{IMAGE_USE_INFO[lang]}</p>\n"
    )
