"""
Genera la guia de desplegament en PDF per al departament de sistemes.
Desplegament en Ubuntu Server amb Apache + Gunicorn (uvicorn workers) + PostgreSQL.
Segueix la mateixa convencio que `fitxes-tecniques` i `comandes-venda`.
Requereix: reportlab

Ús:
    python scripts/genera_pdf_desplegament.py
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, Preformatted, HRFlowable
)
from reportlab.platypus.flowables import Flowable

# --- Colors ---
PRIMARY = HexColor("#1a365d")
PRIMARY_LIGHT = HexColor("#2563eb")
BG_SECTION = HexColor("#f0f4f8")
TEXT_DARK = HexColor("#1a1a1a")
TEXT_GREY = HexColor("#555555")
TEXT_LIGHT = HexColor("#888888")
BORDER = HexColor("#cbd5e0")
CODE_BG = HexColor("#f1f5f9")
WARNING_BG = HexColor("#fefce8")
WARNING_BORDER = HexColor("#ca8a04")
INFO_BG = HexColor("#eff6ff")
INFO_BORDER = HexColor("#3b82f6")
SUCCESS_BG = HexColor("#ecfdf5")
SUCCESS_BORDER = HexColor("#10b981")
WHITE = white

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PDF = os.path.join(BASE_DIR, "docs", "Registre_Visites_Guia_Desplegament_Ubuntu.pdf")
LOGO_PATH = os.path.join(BASE_DIR, "static", "logo.png")

# Configuració del projecte
GITHUB_URL = "https://github.com/ohijazo/RegistreVisites"
APP_NAME = "Registre de Visites"
APP_SLUG = "visites"
INSTALL_DIR = "/var/www/visites"
SERVICE_NAME = "visites"
DB_NAME = "visites_db"
DB_USER = "visites_user"
SERVER_NAME = "visitesfc.agrienergia.local"
APP_PORT = "50003"


class SectionBanner(Flowable):
    def __init__(self, text, width=170*mm):
        super().__init__()
        self.text = text
        self.width = width
        self.height = 10*mm

    def draw(self):
        self.canv.setFillColor(PRIMARY)
        self.canv.roundRect(0, 0, self.width, self.height, 2*mm, fill=1, stroke=0)
        self.canv.setFillColor(WHITE)
        self.canv.setFont("Helvetica-Bold", 13)
        self.canv.drawString(4*mm, 2.8*mm, self.text)


class SubSectionBar(Flowable):
    def __init__(self, text, width=170*mm):
        super().__init__()
        self.text = text
        self.width = width
        self.height = 7*mm

    def draw(self):
        self.canv.setFillColor(BG_SECTION)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        self.canv.setFillColor(PRIMARY_LIGHT)
        self.canv.rect(0, 0, 1.5*mm, self.height, fill=1, stroke=0)
        self.canv.setFillColor(TEXT_DARK)
        self.canv.setFont("Helvetica-Bold", 10)
        self.canv.drawString(5*mm, 2*mm, self.text)


class _Box(Flowable):
    """Caixa amb fons i marc per a avisos / notes."""
    def __init__(self, text, bg, border, width=170*mm):
        super().__init__()
        self.text = text
        self.width = width
        self.height = 0
        self.bg = bg
        self.border = border

    def wrap(self, availWidth, availHeight):
        self.width = min(self.width, availWidth)
        lines = len(self.text) / 80 + 1
        self.height = max(10*mm, lines * 4*mm + 6*mm)
        return (self.width, self.height)

    def draw(self):
        self.canv.setFillColor(self.bg)
        self.canv.roundRect(0, 0, self.width, self.height, 2*mm, fill=1, stroke=0)
        self.canv.setStrokeColor(self.border)
        self.canv.setLineWidth(0.75)
        self.canv.roundRect(0, 0, self.width, self.height, 2*mm, fill=0, stroke=1)
        self.canv.setFillColor(TEXT_DARK)
        self.canv.setFont("Helvetica", 8.5)
        words = self.text.split()
        line = ""
        y = self.height - 5*mm
        for word in words:
            test = line + " " + word if line else word
            if self.canv.stringWidth(test, "Helvetica", 8.5) < self.width - 8*mm:
                line = test
            else:
                self.canv.drawString(4*mm, y, line)
                y -= 3.5*mm
                line = word
        if line:
            self.canv.drawString(4*mm, y, line)


def WarningBox(text):
    return _Box(text, WARNING_BG, WARNING_BORDER)


def InfoBox(text):
    return _Box(text, INFO_BG, INFO_BORDER)


def SuccessBox(text):
    return _Box(text, SUCCESS_BG, SUCCESS_BORDER)


def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "DocTitle", parent=styles["Title"],
        fontSize=28, textColor=PRIMARY, spaceAfter=2*mm,
        fontName="Helvetica-Bold", alignment=TA_LEFT
    ))
    styles.add(ParagraphStyle(
        "DocSubtitle", parent=styles["Normal"],
        fontSize=12, textColor=TEXT_GREY, spaceAfter=6*mm,
        fontName="Helvetica", alignment=TA_LEFT
    ))
    styles.add(ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9.5, textColor=TEXT_DARK, leading=14,
        spaceAfter=2*mm, alignment=TA_JUSTIFY, fontName="Helvetica"
    ))
    styles.add(ParagraphStyle(
        "BulletItem", parent=styles["Normal"],
        fontSize=9.5, textColor=TEXT_DARK, leading=14,
        leftIndent=8*mm, bulletIndent=3*mm, spaceAfter=1.5*mm,
        fontName="Helvetica"
    ))
    styles.add(ParagraphStyle(
        "CodeBlock", parent=styles["Normal"],
        fontSize=8.5, textColor=TEXT_DARK, leading=12,
        fontName="Courier", backColor=CODE_BG,
        leftIndent=4*mm, rightIndent=4*mm,
        spaceBefore=2*mm, spaceAfter=2*mm,
        borderPadding=(3*mm, 3*mm, 3*mm, 3*mm),
    ))
    styles.add(ParagraphStyle(
        "StepTitle", parent=styles["Normal"],
        fontSize=10, textColor=PRIMARY, fontName="Helvetica-Bold",
        spaceAfter=1*mm, spaceBefore=3*mm
    ))
    styles.add(ParagraphStyle(
        "TableHeader", parent=styles["Normal"],
        fontSize=9, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_LEFT
    ))
    styles.add(ParagraphStyle(
        "TableCell", parent=styles["Normal"],
        fontSize=9, textColor=TEXT_DARK, fontName="Helvetica", alignment=TA_LEFT, leading=12
    ))
    styles.add(ParagraphStyle(
        "TableCellBold", parent=styles["Normal"],
        fontSize=9, textColor=TEXT_DARK, fontName="Helvetica-Bold", alignment=TA_LEFT, leading=12
    ))
    return styles


def make_table(headers, rows, col_widths=None):
    styles = get_styles()
    header_cells = [Paragraph(h, styles["TableHeader"]) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([
            Paragraph(str(cell), styles["TableCellBold"] if i == 0 else styles["TableCell"])
            for i, cell in enumerate(row)
        ])
    if not col_widths:
        col_widths = [170*mm / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BACKGROUND", (0, 1), (-1, -1), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, HexColor("#f8fafc")]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def code_block(text):
    styles = get_styles()
    return Preformatted(text, styles["CodeBlock"])


def build_pdf():
    styles = get_styles()
    story = []

    s = lambda sz: Spacer(1, sz*mm)
    p = lambda text: Paragraph(text, styles["Body"])
    bullet = lambda text: Paragraph(f"• {text}", styles["BulletItem"])
    step = lambda text: Paragraph(text, styles["StepTitle"])

    # ============================================================
    # PORTADA
    # ============================================================
    story.append(s(30))
    if os.path.exists(LOGO_PATH):
        story.append(Image(LOGO_PATH, width=55*mm, height=55*mm, kind="proportional"))
        story.append(s(5))
    story.append(Paragraph("Registre de Visites", styles["DocTitle"]))
    story.append(Paragraph(
        "Guia de Desplegament a Produccio",
        ParagraphStyle("CoverSub", parent=styles["DocSubtitle"], fontSize=16, textColor=PRIMARY_LIGHT)
    ))
    story.append(s(5))
    story.append(HRFlowable(width="60%", thickness=2, color=PRIMARY_LIGHT, spaceAfter=8*mm))
    story.append(Paragraph(
        "Instruccions per a l'equip de sistemes<br/>"
        "Desplegament en Ubuntu Server amb Apache + Gunicorn + PostgreSQL",
        ParagraphStyle("CoverDesc", parent=styles["Body"], fontSize=12, textColor=TEXT_GREY)
    ))
    story.append(s(15))

    cover_data = [
        ["Versio", "2.0"],
        ["Data", "Maig 2026"],
        ["Entorn", "Ubuntu Server 24.04 LTS + Apache 2.4 + Gunicorn + PostgreSQL"],
        ["Stack", "Python 3.11+ / FastAPI / SQLAlchemy async"],
        ["Port backend", APP_PORT],
        ["DNS intern", SERVER_NAME],
        ["Directori", INSTALL_DIR],
        ["Repositori", GITHUB_URL],
        ["Destinatari", "Equip de Sistemes - Farinera Coromina"],
    ]
    ct = Table(cover_data, colWidths=[40*mm, 130*mm])
    ct.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER),
    ]))
    story.append(ct)
    story.append(PageBreak())

    # ============================================================
    # 1. INTRODUCCIO
    # ============================================================
    story.append(SectionBanner("1. Sobre l'aplicacio"))
    story.append(s(4))
    story.append(p(
        "<b>Registre de Visites</b> es una aplicacio web en Python que digitalitza el registre "
        "d'entrada i sortida de visitants a les instal.lacions de Farinera Coromina. "
        "Substitueix el registre en paper i compleix amb el RGPD (xifrat de DNI, "
        "consentiment registrat, purga automatica > 2 anys)."
    ))
    story.append(s(2))
    story.append(p(
        "El sistema te dos canals d'acces:"
    ))
    story.append(bullet(
        "<b>Frontal de visitants</b> — Tablet fixa a recepcio en mode quiosc. "
        "El visitant es registra (idioma, dades, motiu, departament, acceptacio RGPD) "
        "i rep un PIN per a registrar la sortida quan se'n vagi."
    ))
    story.append(bullet(
        "<b>Back-office / Administracio</b> — Accessible des de qualsevol PC del personal intern "
        "amb login. Permet veure visites actives en temps real, historial, estadistiques, "
        "gestionar departaments i textos legals, i exportar dades."
    ))
    story.append(s(2))
    story.append(p(
        "Opcionalment, l'app pot enviar una notificacio per email al departament que rep la visita."
    ))
    story.append(s(4))

    story.append(SubSectionBar("Arquitectura"))
    story.append(s(2))
    story.append(code_block(
        "  FRONTAL VISITANTS                      BACK-OFFICE / ADMINISTRACIO\n"
        "  Tablet a recepcio                      PC del personal intern\n"
        "  (navegador Chrome, mode quiosc)        (navegador, login admin)\n"
        "         |                                          |\n"
        "         | registre d'entrada / sortida             | dashboard, historial,\n"
        "         | (formulari + textos legals + PIN)        | estadistiques, exportacio\n"
        "         |                                          |\n"
        "         +------------------+-----------------------+\n"
        "                            |\n"
        "                            v\n"
        "                    Apache 2.4 (port 80)\n"
        "                            |\n"
        "                            v\n"
        f"          Gunicorn + Uvicorn workers (127.0.0.1:{APP_PORT})\n"
        "                       (servei systemd)\n"
        "                            |\n"
        "                            v\n"
        "                    PostgreSQL (port 5432)\n"
        "                    + storage xifrat DNI (AES-256-GCM)"
    ))
    story.append(s(4))

    story.append(SubSectionBar("Components"))
    story.append(s(2))
    story.append(make_table(
        ["Component", "Versio", "Funcio"],
        [
            ["Ubuntu Server", "22.04 / 24.04 LTS", "Sistema operatiu"],
            ["Python", "3.11+", "Executa el backend (FastAPI async)"],
            ["PostgreSQL", "14+", "Base de dades (asyncpg)"],
            ["Apache", "2.4+", "Reverse proxy + headers de seguretat"],
            ["Gunicorn", "22+", "Process manager (uvicorn workers)"],
            ["Git", "2.40+", "Descarregar i actualitzar el codi"],
        ],
        col_widths=[40*mm, 35*mm, 95*mm]
    ))
    story.append(s(3))
    story.append(InfoBox(
        "NOTA: A diferencia d'altres aplicacions internes, aquesta NO te frontend separat. "
        "Les pagines son generades pel servidor amb Jinja2 + HTMX + Tailwind (via CDN). "
        "No cal Node.js ni compilacio de cap fitxer estatic."
    ))
    story.append(PageBreak())

    # ============================================================
    # 2. REQUISITS DE LA MAQUINA
    # ============================================================
    story.append(SectionBanner("2. Requisits de la Maquina Virtual"))
    story.append(s(4))
    story.append(p(
        "L'aplicacio es lleugera. Pot conviure perfectament amb altres aplicacions Python al "
        "mateix servidor (per exemple, la Preparacio de Comandes o les Fitxes Tecniques) "
        "compartint PostgreSQL i Apache."
    ))
    story.append(s(3))

    story.append(SubSectionBar("Especificacions recomanades"))
    story.append(s(2))
    story.append(make_table(
        ["Recurs", "Minim", "Recomanat"],
        [
            ["CPU", "2 cores", "2-4 cores"],
            ["RAM", "1 GB", "2 GB (compartit amb altres apps)"],
            ["Disc", "10 GB", "30 GB SSD"],
            ["Sistema Operatiu", "Ubuntu Server 22.04 LTS", "Ubuntu Server 24.04 LTS"],
            ["Xarxa", "Connectivitat LAN", "IP fixa a la xarxa local"],
        ],
        col_widths=[40*mm, 50*mm, 80*mm]
    ))
    story.append(s(3))
    story.append(InfoBox(
        "Si ja hi ha un servidor Ubuntu amb PostgreSQL i Apache (com l'existent per a "
        "Preparacio de Comandes / Fitxes Tecniques), aquesta aplicacio s'instal.la pel "
        "mateix patro reaprofitant tota la infraestructura. No cal una maquina nova."
    ))
    story.append(s(4))

    story.append(SubSectionBar("Consum estimat"))
    story.append(s(2))
    story.append(make_table(
        ["Component", "Consum", "Observacions"],
        [
            ["Gunicorn + 2 workers", "~150 MB RAM", "Suficient per a ~20 visites simultanies"],
            ["PostgreSQL (BD propia)", "< 50 MB disc/any", "Purga automatica > 2 anys (RGPD)"],
            ["Codi de l'aplicacio", "< 50 MB disc", "Codi + plantilles + translations"],
            ["Logs", "< 100 MB/any", "Rotacio via logrotate (Apache i app)"],
        ],
        col_widths=[55*mm, 35*mm, 80*mm]
    ))
    story.append(PageBreak())

    # ============================================================
    # 3. INSTALACIO DE PAQUETS
    # ============================================================
    story.append(SectionBanner("3. Instal.lacio de Paquets de Sistema"))
    story.append(s(4))
    story.append(p(
        "Si el servidor ja te aquestes versions instal.lades, es pot saltar aquest pas i "
        "passar directament al pas 4 (Base de Dades)."
    ))
    story.append(s(3))

    story.append(step("Pas 3.1 - Actualitzar el sistema"))
    story.append(code_block(
        "sudo apt update && sudo apt upgrade -y"
    ))
    story.append(s(3))

    story.append(step("Pas 3.2 - Instal.lar paquets necessaris"))
    story.append(code_block(
        "# Python (3.11+), pip, venv\n"
        "sudo apt install -y python3 python3-pip python3-venv python3-dev\n"
        "\n"
        "# PostgreSQL (si no esta instal.lat)\n"
        "sudo apt install -y postgresql postgresql-contrib\n"
        "\n"
        "# Apache (si no esta instal.lat) + moduls de proxy\n"
        "sudo apt install -y apache2\n"
        "sudo a2enmod proxy proxy_http headers rewrite expires\n"
        "\n"
        "# Git i build tools (per a algunes dependencies natives)\n"
        "sudo apt install -y git build-essential libpq-dev"
    ))
    story.append(s(3))

    story.append(step("Pas 3.3 - Verificar instal.lacions"))
    story.append(code_block(
        "python3 --version    # 3.11+\n"
        "psql --version       # 14+\n"
        "apache2 -v           # 2.4+\n"
        "git --version        # 2.40+"
    ))
    story.append(PageBreak())

    # ============================================================
    # 4. BASE DE DADES
    # ============================================================
    story.append(SectionBanner("4. Configurar PostgreSQL"))
    story.append(s(4))
    story.append(p(
        "L'aplicacio fa servir una base de dades propia anomenada "
        f"<b>{DB_NAME}</b> dins del PostgreSQL existent. No interfereix amb cap altra "
        "base de dades del servidor."
    ))
    story.append(s(3))

    story.append(step("Pas 4.1 - Crear la base de dades i l'usuari"))
    story.append(code_block(
        f"sudo -u postgres psql <<EOF\n"
        f"CREATE DATABASE {DB_NAME};\n"
        f"CREATE USER {DB_USER} WITH PASSWORD 'CANVIAR_CONTRASENYA_SEGURA';\n"
        f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};\n"
        f"\n"
        f"\\c {DB_NAME}\n"
        f"ALTER DATABASE {DB_NAME} OWNER TO {DB_USER};\n"
        f"ALTER SCHEMA public OWNER TO {DB_USER};\n"
        f"GRANT ALL ON SCHEMA public TO {DB_USER};\n"
        f"GRANT CREATE ON SCHEMA public TO {DB_USER};\n"
        f"EOF"
    ))
    story.append(s(2))
    story.append(WarningBox(
        "IMPORTANT (PostgreSQL 15+): l'esquema 'public' no es escrivible per defecte "
        "encara que es tinguin ALL PRIVILEGES sobre la base de dades. Cal canviar-ne "
        "el propietari (ALTER SCHEMA public OWNER) i donar CREATE. Si no, "
        "'alembic upgrade head' fallara amb 'permission denied for schema public'."
    ))
    story.append(s(2))
    story.append(WarningBox(
        "IMPORTANT: Substituir 'CANVIAR_CONTRASENYA_SEGURA' per una contrasenya real. "
        "Evitar caracters que trenquen URLs (@, :, /, ?, #, ;, espais); si calen, "
        "codificar-los (@ -> %40, : -> %3A, etc.). Anotar la contrasenya per al .env."
    ))
    story.append(s(3))

    story.append(step("Pas 4.2 - Verificar acces"))
    story.append(code_block(
        f"# Provar el login amb el nou usuari\n"
        f"psql -U {DB_USER} -d {DB_NAME} -h localhost -c 'SELECT version();'\n"
        f"# Hauria de mostrar la versio de PostgreSQL i sortir sense errors"
    ))
    story.append(PageBreak())

    # ============================================================
    # 5. DESCARREGAR I CONFIGURAR L'APLICACIO
    # ============================================================
    story.append(SectionBanner("5. Descarregar i Configurar l'Aplicacio"))
    story.append(s(4))

    story.append(step("Pas 5.1 - Clonar el repositori"))
    story.append(code_block(
        f"cd /var/www\n"
        f"sudo git clone {GITHUB_URL}.git {APP_SLUG}\n"
        f"sudo chown -R www-data:www-data {INSTALL_DIR}\n"
        f"\n"
        f"# Carpeta de logs\n"
        f"sudo mkdir -p /var/log/{APP_SLUG}\n"
        f"sudo chown www-data:www-data /var/log/{APP_SLUG}"
    ))
    story.append(s(3))

    story.append(step("Pas 5.2 - Crear l'entorn virtual i instal.lar dependencies"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"sudo -u www-data python3 -m venv venv\n"
        f"sudo -u www-data venv/bin/pip install --upgrade pip\n"
        f"sudo -u www-data venv/bin/pip install -r requirements.txt\n"
        f"sudo -u www-data venv/bin/pip install gunicorn"
    ))
    story.append(s(3))

    story.append(step("Pas 5.3 - Generar claus criptografiques"))
    story.append(s(1))
    story.append(p(
        "Cal generar dues claus aleatories: una per al xifrat AES-256-GCM dels DNI "
        "(<b>ENCRYPTION_KEY</b>) i una per a les sessions JWT i CSRF (<b>SECRET_KEY</b>)."
    ))
    story.append(code_block(
        "# ENCRYPTION_KEY (32 bytes en base64)\n"
        "python3 -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\"\n"
        "\n"
        "# SECRET_KEY (cadena aleatoria llarga)\n"
        "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
    ))
    story.append(s(2))
    story.append(WarningBox(
        "CRITIC: Guardar ENCRYPTION_KEY en lloc segur (gestor de contrasenyes corporatiu). "
        "Si es perd aquesta clau, tots els DNI xifrats a la base de dades quedaran "
        "il.legibles per sempre. Mai canviar-la sense fer abans una migracio dels registres."
    ))
    story.append(s(3))

    story.append(step("Pas 5.4 - Crear el fitxer .env"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"sudo -u www-data cp .env.example .env\n"
        f"sudo nano .env\n"
        f"sudo chmod 600 .env\n"
        f"sudo chown www-data:www-data .env"
    ))
    story.append(s(1))
    story.append(p("Camps obligatoris (substituir els valors entre &lt;&gt;):"))
    story.append(code_block(
        f"# Base de dades\n"
        f"DATABASE_URL=postgresql+asyncpg://{DB_USER}:<CONTRASENYA_BD>@localhost/{DB_NAME}\n"
        f"\n"
        f"# Claus generades al pas 5.3\n"
        f"ENCRYPTION_KEY=<CLAU_GENERADA_AES>\n"
        f"SECRET_KEY=<CLAU_GENERADA_SECRET>\n"
        f"\n"
        f"# Empresa (apareix als textos legals i emails)\n"
        f"COMPANY_NAME=Farinera Coromina - Grup AE 1897\n"
        f"COMPANY_ADDRESS=<Adreca de l'empresa>\n"
        f"COMPANY_EMAIL=dpo@farineracoromina.com\n"
        f"\n"
        f"# URL d'acces dels usuaris (s'usa per generar els QR)\n"
        f"BASE_URL=http://{SERVER_NAME}\n"
        f"\n"
        f"# Sessio admin i tablet\n"
        f"SESSION_HOURS=8\n"
        f"EXIT_TOKEN_HOURS=8\n"
        f"KIOSK_RESET_SECONDS=30\n"
        f"\n"
        f"# Entorn\n"
        f"ENV=production\n"
        f"DEBUG=false"
    ))
    story.append(s(3))

    story.append(step("Pas 5.5 - Executar migracions de base de dades"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"sudo -u www-data venv/bin/alembic upgrade head\n"
        f"# Hauria de crear totes les taules (visits, departments, legal_documents, etc.)"
    ))
    story.append(s(3))

    story.append(step("Pas 5.6 - Crear el primer usuari administrador"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"sudo -u www-data venv/bin/python scripts/create_admin.py \\\n"
        f"    --email admin@farineracoromina.com \\\n"
        f"    --name \"Administrador\""
    ))
    story.append(s(1))
    story.append(p(
        "El script demanara la contrasenya per CLI. Aquesta sera la credencial inicial "
        "per accedir al panell <b>/admin/login</b>. Es pot canviar despres des del panell."
    ))
    story.append(s(3))

    story.append(step("Pas 5.7 - Carregar el document legal RGPD inicial"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"sudo -u www-data venv/bin/python scripts/seed_legal_doc.py"
    ))
    story.append(s(1))
    story.append(p(
        "Aquest script carrega el text legal de visitants i subcontratistes (IT04.03 "
        "Bones Practiques) en els quatre idiomes (CA, ES, FR, EN). Despres es pot "
        "actualitzar des de <b>/admin/legal</b>."
    ))
    story.append(PageBreak())

    # ============================================================
    # 6. VERIFICACIO MANUAL
    # ============================================================
    story.append(SectionBanner("6. Verificacio Manual de l'Aplicacio"))
    story.append(s(4))
    story.append(p(
        "Abans de configurar-la com a servei, conve provar que arrenca correctament "
        "des de la consola:"
    ))
    story.append(s(3))

    story.append(step("Pas 6.1 - Arrencar manualment"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"sudo -u www-data venv/bin/uvicorn app.main:app --host 127.0.0.1 --port {APP_PORT}"
    ))
    story.append(s(3))

    story.append(step("Pas 6.2 - Provar des d'un altre terminal"))
    story.append(code_block(
        f"# Health check\n"
        f"curl http://localhost:{APP_PORT}/health\n"
        f"# Hauria de retornar JSON amb status: ok\n"
        f"\n"
        f"# Pagina principal (redirigeix a /ca/)\n"
        f"curl -I http://localhost:{APP_PORT}/\n"
        f"# Hauria de retornar HTTP/1.1 302 o 307\n"
        f"\n"
        f"# Aturar amb Ctrl+C"
    ))
    story.append(s(3))
    story.append(SuccessBox(
        "Si els dos comandes retornen una resposta valida, l'aplicacio funciona. "
        "El seguent pas es deixar-la corrent de forma permanent com a servei systemd."
    ))
    story.append(PageBreak())

    # ============================================================
    # 7. SERVEI SYSTEMD
    # ============================================================
    story.append(SectionBanner("7. Configurar com a Servei (systemd)"))
    story.append(s(4))
    story.append(p(
        "Per garantir que l'aplicacio s'arrenqui automaticament amb la maquina i es "
        "reinicii si cau, es registra com a servei <b>systemd</b>. Es fa servir "
        "<b>Gunicorn</b> amb workers <b>Uvicorn</b> (el patro recomanat per FastAPI en produccio)."
    ))
    story.append(s(3))

    story.append(step("Pas 7.1 - Verificar permisos"))
    story.append(code_block(
        f"# La carpeta de logs i el codi ja son de www-data del pas 5.1\n"
        f"# Verificar:\n"
        f"ls -ld {INSTALL_DIR} /var/log/{APP_SLUG}\n"
        f"# Tots dos han de ser propietat de www-data:www-data"
    ))
    story.append(s(3))

    story.append(step("Pas 7.2 - Crear el fitxer de servei"))
    story.append(code_block(
        f"sudo nano /etc/systemd/system/{SERVICE_NAME}.service"
    ))
    story.append(s(1))
    story.append(p("Contingut:"))
    story.append(code_block(
        f"[Unit]\n"
        f"Description=Registre de Visites - Backend\n"
        f"After=network.target postgresql.service\n"
        f"Requires=postgresql.service\n"
        f"\n"
        f"[Service]\n"
        f"Type=exec\n"
        f"User=www-data\n"
        f"Group=www-data\n"
        f"WorkingDirectory={INSTALL_DIR}\n"
        f"EnvironmentFile={INSTALL_DIR}/.env\n"
        f"ExecStart={INSTALL_DIR}/venv/bin/gunicorn app.main:app \\\n"
        f"    --workers 2 \\\n"
        f"    --worker-class uvicorn.workers.UvicornWorker \\\n"
        f"    --bind 127.0.0.1:{APP_PORT} \\\n"
        f"    --timeout 30 \\\n"
        f"    --access-logfile /var/log/{APP_SLUG}/access.log \\\n"
        f"    --error-logfile /var/log/{APP_SLUG}/error.log\n"
        f"ExecReload=/bin/kill -s HUP $MAINPID\n"
        f"Restart=always\n"
        f"RestartSec=5\n"
        f"\n"
        f"[Install]\n"
        f"WantedBy=multi-user.target"
    ))
    story.append(s(3))

    story.append(step("Pas 7.3 - Activar i arrencar el servei"))
    story.append(code_block(
        f"sudo systemctl daemon-reload\n"
        f"sudo systemctl enable {SERVICE_NAME}\n"
        f"sudo systemctl start {SERVICE_NAME}\n"
        f"sudo systemctl status {SERVICE_NAME}\n"
        f"# Hauria de dir: active (running)"
    ))
    story.append(s(3))

    story.append(SubSectionBar("Comandes de gestio del servei"))
    story.append(s(2))
    story.append(make_table(
        ["Comanda", "Accio"],
        [
            [f"sudo systemctl start {SERVICE_NAME}",       "Arrencar el servei"],
            [f"sudo systemctl stop {SERVICE_NAME}",        "Aturar el servei"],
            [f"sudo systemctl restart {SERVICE_NAME}",     "Reiniciar el servei"],
            [f"sudo systemctl status {SERVICE_NAME}",      "Veure l'estat"],
            [f"sudo journalctl -u {SERVICE_NAME} -f",      "Logs en temps real (journald)"],
            [f"sudo tail -f /var/log/{APP_SLUG}/error.log","Logs d'errors de Gunicorn"],
            [f"sudo systemctl disable {SERVICE_NAME}",     "Desactivar arrencada automatica"],
        ],
        col_widths=[70*mm, 100*mm]
    ))
    story.append(PageBreak())

    # ============================================================
    # 8. APACHE
    # ============================================================
    story.append(SectionBanner("8. Configurar Apache (Reverse Proxy)"))
    story.append(s(4))
    story.append(p(
        "Apache fa de reverse proxy davant del Gunicorn, gestiona els fitxers estatics i "
        "afegeix els headers de seguretat. Segueix exactament el mateix patro que les "
        "aplicacions germanes <b>fitxes-tecniques</b> i <b>comandes-venda</b>."
    ))
    story.append(s(3))

    story.append(step("Pas 8.1 - Activar moduls necessaris (si no s'han activat al pas 3.2)"))
    story.append(code_block(
        "sudo a2enmod proxy proxy_http headers rewrite expires\n"
        "sudo systemctl restart apache2"
    ))
    story.append(s(3))

    story.append(step("Pas 8.2 - Crear el VirtualHost"))
    story.append(code_block(
        f"sudo nano /etc/apache2/sites-available/{APP_SLUG}.conf"
    ))
    story.append(s(1))
    story.append(p("Contingut:"))
    story.append(code_block(
        f"<VirtualHost *:80>\n"
        f"    ServerName {SERVER_NAME}\n"
        f"\n"
        f"    # Headers de seguretat\n"
        f"    Header always set X-Frame-Options        \"DENY\"\n"
        f"    Header always set X-Content-Type-Options \"nosniff\"\n"
        f"    Header always set Referrer-Policy        \"strict-origin\"\n"
        f"\n"
        f"    # Limit de mida dels POST (formulari amb foto opcional)\n"
        f"    LimitRequestBody 2097152\n"
        f"\n"
        f"    # Fitxers estatics servits directament per Apache\n"
        f"    Alias /static/ {INSTALL_DIR}/static/\n"
        f"    <Directory {INSTALL_DIR}/static/>\n"
        f"        Require all granted\n"
        f"        Options -Indexes\n"
        f"        ExpiresActive On\n"
        f"        ExpiresDefault \"access plus 30 days\"\n"
        f"    </Directory>\n"
        f"\n"
        f"    # Reverse proxy a Gunicorn (NO incloure /static/)\n"
        f"    ProxyPreserveHost On\n"
        f"    ProxyPass        /static/ !\n"
        f"    ProxyPass        / http://127.0.0.1:{APP_PORT}/\n"
        f"    ProxyPassReverse / http://127.0.0.1:{APP_PORT}/\n"
        f"\n"
        f"    # Capcaleres per a que el backend sapiga la IP real del visitant\n"
        f"    RequestHeader set X-Forwarded-Proto \"http\"\n"
        f"\n"
        f"    ErrorLog  ${{APACHE_LOG_DIR}}/{APP_SLUG}-error.log\n"
        f"    CustomLog ${{APACHE_LOG_DIR}}/{APP_SLUG}-access.log combined\n"
        f"</VirtualHost>"
    ))
    story.append(s(3))

    story.append(step("Pas 8.3 - Activar el site i recarregar Apache"))
    story.append(code_block(
        f"# Activar el site\n"
        f"sudo a2ensite {APP_SLUG}.conf\n"
        f"\n"
        f"# Validar la sintaxi\n"
        f"sudo apache2ctl configtest\n"
        f"# Hauria de dir: Syntax OK\n"
        f"\n"
        f"# Recarregar Apache (sense interrompre les altres apps)\n"
        f"sudo systemctl reload apache2"
    ))
    story.append(s(3))
    story.append(InfoBox(
        "Si el servidor ja te altres apps darrere d'Apache (com fitxes-tecniques o "
        "comandes-venda), aquest patro de sites-available + a2ensite permet afegir una "
        "app nova sense modificar res del que ja funciona."
    ))
    story.append(PageBreak())

    # ============================================================
    # 9. XARXA, DNS I FIREWALL
    # ============================================================
    story.append(SectionBanner("9. Xarxa, DNS i Firewall"))
    story.append(s(4))

    story.append(SubSectionBar("Firewall (UFW)"))
    story.append(s(2))
    story.append(p(
        "Si el firewall UFW esta actiu (comprovar amb <b>sudo ufw status</b>), nomes cal "
        "verificar que el port 80 i el SSH estan oberts. Cap port nou per a aquesta app."
    ))
    story.append(code_block(
        "sudo ufw allow ssh\n"
        "sudo ufw allow 80/tcp\n"
        "sudo ufw status"
    ))
    story.append(s(1))
    story.append(p(
        f"<b>No cal obrir el port {APP_PORT}</b> - Gunicorn nomes escolta a 127.0.0.1 "
        f"i nomes Apache hi pot accedir."
    ))
    story.append(s(4))

    story.append(SubSectionBar("DNS intern"))
    story.append(s(2))
    story.append(p(
        "Crear una entrada al servidor DNS de l'empresa per a que la tablet i els mobils "
        "dels visitants puguin accedir per nom (mes facil de codificar als QR que una IP):"
    ))
    story.append(code_block(
        f"Tipus:   A\n"
        f"Nom:     {SERVER_NAME}\n"
        f"Valor:   <IP-DEL-SERVIDOR>      # p.ex. 192.168.1.50"
    ))
    story.append(s(2))
    story.append(WarningBox(
        f"La variable BASE_URL del fitxer .env ha de coincidir EXACTAMENT amb la URL que "
        f"acaba a la tablet (p.ex. http://{SERVER_NAME}). Si canvies aqui, "
        f"actualitza tambe el .env i reinicia el servei: sudo systemctl restart {SERVICE_NAME}."
    ))
    story.append(PageBreak())

    # ============================================================
    # 10. EMAIL (OPCIONAL)
    # ============================================================
    story.append(SectionBanner("10. Email de Notificacio (opcional)"))
    story.append(s(4))
    story.append(p(
        "Quan es crea una visita prevista des de l'admin, l'app pot enviar un avis per "
        "email al departament que rep la visita. Es opcional: si no es configura, "
        "l'aplicacio funciona igual pero sense enviar emails."
    ))
    story.append(s(2))
    story.append(p(
        "Hi ha dues opcions per integrar amb Microsoft 365 (recomanat respecte SMTP, que "
        "esta sent deprecat per Microsoft):"
    ))
    story.append(s(3))

    story.append(SubSectionBar("Opcio A - Power Automate (rapid)"))
    story.append(s(2))
    story.append(p(
        "Crear un flux instantani a <b>make.powerautomate.com</b> amb trigger HTTP "
        "que rebi un JSON i envii email amb el connector \"Office 365 Outlook\". L'app "
        "fa una crida POST a l'URL del webhook. Variables al .env:"
    ))
    story.append(code_block(
        "EMAIL_BACKEND=power_automate\n"
        "POWER_AUTOMATE_WEBHOOK_URL=https://prod-XX.westeurope.logic.azure.com:443/...\n"
        "POWER_AUTOMATE_SECRET=<un-string-llarg-aleatori>\n"
        "EXPECTED_NOTIFY_RECIPIENTS=cap@empresa.com,recepcio@empresa.com"
    ))
    story.append(s(3))

    story.append(SubSectionBar("Opcio B - Microsoft Graph API (recomanat a llarg termini)"))
    story.append(s(2))
    story.append(p(
        "Registrar una app a <b>entra.microsoft.com</b> amb permis d'aplicacio "
        "<b>Mail.Send</b>, restringida a una sola bustia amb ApplicationAccessPolicy. "
        "Variables al .env:"
    ))
    story.append(code_block(
        "EMAIL_BACKEND=graph_ms\n"
        "MS_TENANT_ID=<directory_tenant_id>\n"
        "MS_CLIENT_ID=<application_client_id>\n"
        "MS_CLIENT_SECRET=<valor_del_secret>\n"
        "MS_SENDER_EMAIL=coromina@empresa.com\n"
        "EXPECTED_NOTIFY_RECIPIENTS=cap@empresa.com,recepcio@empresa.com"
    ))
    story.append(s(2))
    story.append(InfoBox(
        "Veure el detall pas a pas (apartats 11 i 12) al fitxer DEPLOY.md del repositori. "
        "Despres de canviar el .env, sempre reiniciar: sudo systemctl restart visites."
    ))
    story.append(s(3))

    story.append(SubSectionBar("Verificacio"))
    story.append(s(2))
    story.append(p(
        "Crear una visita prevista des de <b>/admin/expected/new</b> i comprovar:"
    ))
    story.append(bullet("L'email arriba al destinatari (mirar tambe la carpeta Spam)"))
    story.append(bullet("<b>/admin/audit-logs?action=expected_visit_email_sent_auto</b> mostra la traca"))
    story.append(bullet("Si falla, mirar <b>action=expected_visit_email_failed_auto</b> per veure l'error"))
    story.append(PageBreak())

    # ============================================================
    # 11. CRON DE MANTENIMENT
    # ============================================================
    story.append(SectionBanner("11. Tasques Programades (cron)"))
    story.append(s(4))
    story.append(p(
        "Dues tasques nocturnes son indispensables: tancar visites que s'han quedat "
        "obertes (visitant ha marxat sense fer checkout) i purgar registres de mes "
        "de 2 anys segons RGPD (article 5.1.e)."
    ))
    story.append(s(3))

    story.append(step("Pas 11.1 - Editar el crontab de www-data"))
    story.append(code_block(
        "sudo crontab -u www-data -e"
    ))
    story.append(s(2))
    story.append(p(
        "Afegir aquestes linies (les tres primeres son variables per escurcar la "
        "resta - es el patro estandard de crontab):"
    ))
    story.append(code_block(
        f"PY={INSTALL_DIR}/venv/bin/python\n"
        f"APP={INSTALL_DIR}\n"
        f"LOGS=/var/log/{APP_SLUG}\n"
        f"\n"
        f"# Auto-checkout nocturn: tanca visites obertes > 12h\n"
        f"55 23 * * * $PY $APP/scripts/auto_close_visits.py >> $LOGS/auto_close.log 2>&1\n"
        f"\n"
        f"# Neteja RGPD: elimina visites > 2 anys (article 5.1.e)\n"
        f"0 3 * * * $PY $APP/scripts/purge_old_visits.py >> $LOGS/purge.log 2>&1"
    ))
    story.append(s(4))

    story.append(SubSectionBar("Backup diari de la base de dades"))
    story.append(s(2))
    story.append(p(
        "Recomanat per politica de l'empresa. Backup automatic cada nit i retencio "
        "de 30 dies:"
    ))
    story.append(code_block(
        "sudo mkdir -p /opt/backups/visites\n"
        "sudo chown postgres:postgres /opt/backups/visites"
    ))
    story.append(s(2))
    story.append(p("Crear el fitxer de cron de sistema:"))
    story.append(code_block(
        f"sudo nano /etc/cron.d/{APP_SLUG}-backup"
    ))
    story.append(s(1))
    story.append(p("Contingut (atencio: els <b>\\%</b> son necessaris perque cron interpreta <b>%</b> com a salts de linia):"))
    story.append(code_block(
        f"BACKUP_DIR=/opt/backups/visites\n"
        f"\n"
        f"# Backup diari a les 02:00\n"
        f"0 2 * * * postgres pg_dump {DB_NAME} | \\\n"
        f"          gzip > $BACKUP_DIR/visites_$(date +\\%Y\\%m\\%d).sql.gz\n"
        f"\n"
        f"# Eliminar backups > 30 dies (a les 03:00)\n"
        f"0 3 * * * root find $BACKUP_DIR -name \"*.sql.gz\" -mtime +30 -delete"
    ))
    story.append(PageBreak())

    # ============================================================
    # 12. VERIFICACIO FINAL
    # ============================================================
    story.append(SectionBanner("12. Verificacio Final"))
    story.append(s(4))

    story.append(step("Checklist de verificacio"))
    story.append(s(2))
    story.append(make_table(
        ["#", "Verificacio", "Com comprovar-ho"],
        [
            ["1", "PostgreSQL actiu",         "sudo systemctl status postgresql"],
            ["2", "Aplicacio activa",         f"sudo systemctl status {SERVICE_NAME}"],
            ["3", "Apache actiu",             "sudo systemctl status apache2"],
            ["4", "Health check",             f"curl http://localhost:{APP_PORT}/health"],
            ["5", "Acces des de tablet",      f"Obrir http://{SERVER_NAME} al navegador"],
            ["6", "Login admin",              f"http://{SERVER_NAME}/admin/login"],
            ["7", "Formulari visitant",       "Completar registre des de la tablet"],
            ["8", "QR de sortida funciona",   "Escanejar el QR amb el mobil"],
            ["9", "PIN de sortida funciona",  f"http://{SERVER_NAME}/checkout amb el PIN"],
            ["10","Servei resisteix reboot",  "sudo reboot i verificar acces despres"],
        ],
        col_widths=[10*mm, 50*mm, 110*mm]
    ))
    story.append(s(4))

    story.append(step("Prova completa des d'un dispositiu"))
    story.append(s(1))
    story.append(p(
        "Des d'una tablet o PC de la xarxa local, obrir el navegador i anar a:"
    ))
    story.append(code_block(f"http://{SERVER_NAME}"))
    story.append(p(
        "Hauria d'apareixer la pantalla de seleccio d'idioma (CA / ES / FR / EN). "
        "Completar el flux de registre i verificar que es genera un QR i un PIN. "
        "Despres, des de <b>/checkout</b> introduir el PIN per registrar la sortida."
    ))
    story.append(PageBreak())

    # ============================================================
    # 13. MANTENIMENT
    # ============================================================
    story.append(SectionBanner("13. Manteniment i Actualitzacions"))
    story.append(s(4))

    story.append(SubSectionBar("Actualitzar l'aplicacio"))
    story.append(s(2))
    story.append(p("Quan es lliuri una nova versio:"))
    story.append(code_block(
        f"cd {INSTALL_DIR}\n"
        f"\n"
        f"# 1. Descarregar canvis\n"
        f"sudo -u www-data git pull\n"
        f"\n"
        f"# 2. Actualitzar dependencies (si requirements.txt ha canviat)\n"
        f"sudo -u www-data {INSTALL_DIR}/venv/bin/pip install -r requirements.txt\n"
        f"\n"
        f"# 3. Aplicar noves migracions (si n'hi ha)\n"
        f"sudo -u www-data {INSTALL_DIR}/venv/bin/alembic upgrade head\n"
        f"\n"
        f"# 4. Restaurar permisos i reiniciar\n"
        f"sudo chown -R www-data:www-data {INSTALL_DIR}\n"
        f"sudo systemctl restart {SERVICE_NAME}\n"
        f"\n"
        f"# 5. Verificar\n"
        f"sudo systemctl status {SERVICE_NAME}\n"
        f"curl http://localhost:{APP_PORT}/health"
    ))
    story.append(s(4))

    story.append(SubSectionBar("Logs - ubicacions"))
    story.append(s(2))
    story.append(make_table(
        ["Log", "Ubicacio"],
        [
            ["Gunicorn - acces",       f"/var/log/{APP_SLUG}/access.log"],
            ["Gunicorn - errors",      f"/var/log/{APP_SLUG}/error.log"],
            ["systemd (journald)",     f"sudo journalctl -u {SERVICE_NAME} -f"],
            ["Apache - acces",         f"/var/log/apache2/{APP_SLUG}-access.log"],
            ["Apache - errors",        f"/var/log/apache2/{APP_SLUG}-error.log"],
            ["Cron - auto-checkout",   f"/var/log/{APP_SLUG}/auto_close.log"],
            ["Cron - purga RGPD",      f"/var/log/{APP_SLUG}/purge.log"],
            ["PostgreSQL",             "/var/log/postgresql/"],
        ],
        col_widths=[55*mm, 115*mm]
    ))
    story.append(s(4))

    story.append(SubSectionBar("Resolucio de problemes"))
    story.append(s(2))
    story.append(make_table(
        ["Sintoma", "Causa probable / Solucio"],
        [
            ["Servei no arrenca",
             f"Mirar /var/log/{APP_SLUG}/error.log o journalctl -u {SERVICE_NAME} -n 50"],
            ["Error 502/503 a Apache",
             f"Gunicorn caigut: sudo systemctl restart {SERVICE_NAME}"],
            ["Error de BD",
             "Verificar PostgreSQL: sudo systemctl status postgresql"],
            ["Pagina no carrega",
             "Validar Apache: sudo apache2ctl configtest, comprovar firewall"],
            ["Error de xifrat de DNI",
             "Verificar que ENCRYPTION_KEY al .env coincideix amb la que es va usar inicialment"],
            ["DNI sembla illegible",
             "Mai canviar ENCRYPTION_KEY despres del primer registre. Restaurar backup"],
            ["QR no funciona des del mobil",
             "Verificar que BASE_URL al .env es accessible des de la xarxa Wi-Fi del visitant"],
            ["Tablet es queda penjada",
             "KIOSK_RESET_SECONDS al .env controla el reset automatic"],
        ],
        col_widths=[55*mm, 115*mm]
    ))
    story.append(PageBreak())

    # ============================================================
    # 14. RESUM I CONSIDERACIONS RGPD
    # ============================================================
    story.append(SectionBanner("14. Resum i Consideracions de Seguretat"))
    story.append(s(4))

    story.append(SubSectionBar("Resum de passos"))
    story.append(s(2))
    story.append(make_table(
        ["Pas", "Accio", "Temps estimat"],
        [
            ["1", "Preparar maquina virtual Ubuntu Server 24.04",  "10 min"],
            ["2", "Instal.lar paquets (apt install)",              "10 min"],
            ["3", "Crear BD i usuari PostgreSQL",                  "5 min"],
            ["4", "Clonar repositori i configurar .env",           "10 min"],
            ["5", "Migracions + admin + document legal",           "5 min"],
            ["6", "Verificacio manual amb uvicorn",                "5 min"],
            ["7", "Crear servei systemd (Gunicorn + Uvicorn)",     "5 min"],
            ["8", "Configurar Apache (reverse proxy)",             "5 min"],
            ["9", "DNS intern + firewall",                         "5 min"],
            ["10","Email (opcional, Power Automate o Graph API)",  "15-30 min"],
            ["11","Cron de manteniment + backup diari",            "5 min"],
            ["12","Verificacio final amb tablet",                  "10 min"],
        ],
        col_widths=[12*mm, 118*mm, 40*mm]
    ))
    story.append(s(2))
    story.append(p("<b>Temps total estimat: ~90 minuts</b> (sense comptar Email amb Graph)"))
    story.append(s(4))

    story.append(SubSectionBar("Consideracions de seguretat i RGPD"))
    story.append(s(2))
    story.append(make_table(
        ["Aspecte", "Implementacio"],
        [
            ["Xifrat de DNI",
             "AES-256-GCM amb IV unic per registre. Clau a ENCRYPTION_KEY (.env)"],
            ["Consentiment registrat",
             "legal_document_id + accepted_at + IP + user-agent a cada visita"],
            ["Dret de supressio",
             "Boto a /admin/visits/{id} per eliminar registre individualment"],
            ["Purga automatica",
             "Script purge_old_visits.py via cron, elimina > 2 anys"],
            ["Auditoria d'acces a DNI",
             "Cada desxifrat queda registrat a audit_logs (admin_id, IP, timestamp)"],
            ["Sessions admin",
             "JWT en cookie HttpOnly + SameSite=Strict. Expiracio: SESSION_HOURS"],
            ["CSRF",
             "Token double-submit a tots els POST/PUT/DELETE"],
            ["Rate limiting",
             "Max 10 POST/minut/IP al formulari de registre (slowapi)"],
            ["Headers de seguretat",
             "X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy (a l'app i Apache mod_headers)"],
            ["DNI als logs",
             "Apache (combined log) NO registra el cos del POST. App tampoc loga el camp id_document"],
        ],
        col_widths=[40*mm, 130*mm]
    ))
    story.append(s(6))

    story.append(SubSectionBar("Contacte"))
    story.append(s(2))
    story.append(p(
        "Per a qualsevol incidencia tecnica relacionada amb el desplegament, "
        "contactar amb el responsable del projecte:"
    ))
    story.append(s(1))
    story.append(make_table(
        ["", ""],
        [
            ["Repositori",   GITHUB_URL],
            ["Documentacio", f"{INSTALL_DIR}/DEPLOY.md (versio detallada al repositori)"],
            ["Empresa",      "Farinera Coromina - Grup AE 1897"],
        ],
        col_widths=[40*mm, 130*mm]
    ))

    story.append(s(10))
    story.append(HRFlowable(width="40%", thickness=1, color=BORDER, spaceAfter=4*mm))
    story.append(Paragraph(
        "<i>Document generat el maig de 2026 - Registre de Visites v1.0</i>",
        ParagraphStyle("Footer", parent=styles["Body"], fontSize=8, textColor=TEXT_LIGHT, alignment=TA_CENTER)
    ))

    # ============================================================
    # BUILD
    # ============================================================
    os.makedirs(os.path.dirname(OUTPUT_PDF), exist_ok=True)
    doc = SimpleDocTemplate(
        OUTPUT_PDF,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
    )
    doc.build(story)
    print(f"PDF generat: {OUTPUT_PDF}")


if __name__ == "__main__":
    build_pdf()
