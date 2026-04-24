# CLAUDE.md — Sistema de Registre de Visites

## Resum del projecte

Aplicació web en Python per digitalitzar el registre d'entrada i sortida de visitants a les instal·lacions de l'empresa (fàbrica/oficines). Substitueix el registre en paper. Els visitants s'identifiquen des d'una **tablet fixa a recepció en mode quiosc** (canal principal) o escanejant un **codi QR** amb el seu mòbil (canal alternatiu).

---

## Infraestructura existent (no modificar)

- **Servidor**: Ubuntu (amb altres apps Python en producció)
- **Base de dades**: PostgreSQL ja instal·lat i en ús per altres aplicacions
- **Servidor web**: Nginx ja instal·lat com a reverse proxy
- **Patró de desplegament**: Cada app Python corre com a servei systemd darrere de Nginx

La nova app s'integra seguint exactament el mateix patró. **No trencar res del que ja existeix.**

---

## Comandes essencials

```bash
# Instal·lar dependències
pip install -r requirements.txt

# Crear / actualitzar base de dades
alembic upgrade head

# Arrencar en desenvolupament
uvicorn app.main:app --reload --port 8001

# Arrencar en producció (gunicorn gestiona uvicorn workers)
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8001

# Executar tests
pytest

# Generar nova migració després de canviar models
alembic revision --autogenerate -m "descripció"

# Crear primer usuari admin
python scripts/create_admin.py --email admin@empresa.com --password CANVIAR

# Exportar visites a CSV (manual)
python scripts/export_visits.py --from 2024-01-01 --to 2024-12-31
```

---

## Stack tecnològic

| Capa | Tecnologia | Versió mínima |
|---|---|---|
| Framework web | FastAPI | 0.111 |
| Servidor ASGI | Uvicorn + Gunicorn | 0.29 / 22.0 |
| ORM | SQLAlchemy (async) | 2.0 |
| Migracions BD | Alembic | 1.13 |
| Driver PostgreSQL | asyncpg | 0.29 |
| Plantilles HTML | Jinja2 | 3.1 |
| Interactivitat UI | HTMX | via CDN |
| Estils | Tailwind CSS | via CDN play |
| Multiidioma | Diccionaris JSON propis | — |
| Xifrat DNI | cryptography (AES-256-GCM) | 42.0 |
| Generació QR | qrcode[pil] | 7.4 |
| Export Excel | openpyxl | 3.1 |
| Autenticació admin | python-jose + passlib[bcrypt] | — |
| Formularis | python-multipart | 0.0.9 |
| Tests | pytest + pytest-asyncio + httpx | — |

---

## Estructura de directoris

```
visites/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env.example
├── .env                        # MAI al repositori git
├── .gitignore
│
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial.py
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, inclusió de routers, middleware
│   ├── config.py               # Settings llegits des de .env
│   ├── dependencies.py         # Dependències compartides (get_db, get_current_admin)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # Engine async, SessionLocal, Base
│   │   └── models.py           # Tots els models SQLAlchemy
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── visitor.py          # Formulari i flux del visitant (públic)
│   │   ├── checkout.py         # Registre de sortida (públic)
│   │   └── admin.py            # Panell d'administració (autenticat)
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── visit.py            # Pydantic schemas per a visites
│   │   └── admin.py            # Pydantic schemas per a admin
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── crypto.py           # Xifrat/desxifrat DNI (AES-256-GCM)
│   │   ├── qr.py               # Generació de codis QR (imatge base64)
│   │   ├── i18n.py             # Càrrega i resolució de traduccions
│   │   └── export.py           # Exportació CSV i Excel
│   │
│   └── templates/
│       ├── base.html           # Layout base comú
│       ├── visitor/
│       │   ├── language.html   # Pas 1: selecció d'idioma
│       │   ├── form.html       # Pas 2: formulari de registre
│       │   ├── legal.html      # Pas 3: textos legals + checkboxes
│       │   └── confirmation.html # Pas 4: confirmació + QR + PIN
│       ├── checkout/
│       │   ├── scan.html       # Pantalla d'escaneig QR de sortida
│       │   └── done.html       # Sortida registrada correctament
│       └── admin/
│           ├── login.html
│           ├── dashboard.html  # Vista en temps real
│           ├── visits.html     # Historial i filtres
│           ├── visit_detail.html
│           ├── departments.html
│           ├── legal_docs.html
│           └── users.html
│
├── translations/
│   ├── ca.json                 # Català (per defecte)
│   ├── es.json                 # Castellà
│   ├── fr.json                 # Francès
│   └── en.json                 # Anglès
│
├── static/
│   ├── favicon.ico
│   └── logo.png                # Logo de l'empresa (opcional)
│
├── scripts/
│   ├── create_admin.py         # Crea primer usuari administrador
│   ├── export_visits.py        # Exportació manual per dates
│   └── purge_old_visits.py     # Elimina visites > 2 anys (cridat per cron)
│
└── tests/
    ├── conftest.py
    ├── test_visitor_flow.py
    ├── test_checkout.py
    ├── test_admin.py
    └── test_crypto.py
```

---

## Variables d'entorn (.env)

```dotenv
# Base de dades (nova BD al PostgreSQL existent)
DATABASE_URL=postgresql+asyncpg://visites_user:PASSWORD@localhost/visites_db

# Clau de xifrat per al DNI (AES-256-GCM, 32 bytes en base64)
# Generar: python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
ENCRYPTION_KEY=

# Clau per a JWT sessions admin (cadena aleatòria llarga)
SECRET_KEY=

# Durada sessió admin en hores
SESSION_HOURS=8

# Durada màxima del token de sortida QR en hores
EXIT_TOKEN_HOURS=8

# Minuts d'inactivitat a la tablet fins al reset automàtic
KIOSK_RESET_SECONDS=30

# Nom i adreça de l'empresa (apareix als textos legals)
COMPANY_NAME=
COMPANY_ADDRESS=
COMPANY_EMAIL=dpo@empresa.com

# SMTP per a notificacions (opcional, Fase 2)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=visites@empresa.com

# Entorn
ENV=production
DEBUG=false
```

---

## Models de base de dades (`app/db/models.py`)

```python
import uuid
from datetime import datetime
from sqlalchemy import (Column, String, Boolean, DateTime, Text,
                        ForeignKey, LargeBinary, Integer)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship
from app.db.database import Base

class Location(Base):
    """Ubicació física o punt d'accés. Cada QR d'entrada correspon a una Location."""
    __tablename__ = "locations"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(String(200), nullable=False)   # ex: "Fàbrica - Porta Principal"
    qr_token   = Column(String(64), unique=True, nullable=False)  # token URL del QR entrada
    active     = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    visits     = relationship("Visit", back_populates="location")


class Department(Base):
    """Departaments de l'empresa. El visitant n'escull un al formulari."""
    __tablename__ = "departments"
    id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_ca = Column(String(200), nullable=False)
    name_es = Column(String(200), nullable=False)
    name_fr = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    order   = Column(Integer, default=0)  # ordre a la llista desplegable
    active  = Column(Boolean, default=True)


class LegalDocument(Base):
    """Versió dels textos legals. Sempre n'hi ha una d'activa."""
    __tablename__ = "legal_documents"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_hash = Column(String(64), nullable=False)  # SHA-256 del contingut concatenat
    content_ca   = Column(Text, nullable=False)
    content_es   = Column(Text, nullable=False)
    content_fr   = Column(Text, nullable=False)
    content_en   = Column(Text, nullable=False)
    active       = Column(Boolean, default=False)  # només una activa a la vegada
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)
    visits       = relationship("Visit", back_populates="legal_document")


class Visit(Base):
    """Registre d'una visita. Una fila = una persona en una ocasió."""
    __tablename__ = "visits"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id      = Column(UUID(as_uuid=True), ForeignKey("locations.id"))
    location         = relationship("Location", back_populates="visits")

    # Dades personals
    first_name       = Column(String(100), nullable=False)
    last_name        = Column(String(150), nullable=False)
    company          = Column(String(200), nullable=False)
    id_document_enc  = Column(LargeBinary, nullable=False)  # AES-256-GCM ciphertext
    id_document_iv   = Column(LargeBinary, nullable=False)  # 12 bytes IV (únic per registre)
    phone            = Column(String(30))                   # opcional

    # Visita
    department_id    = Column(UUID(as_uuid=True), ForeignKey("departments.id"))
    department       = relationship("Department")
    visit_reason     = Column(Text, nullable=False)
    language         = Column(String(2), nullable=False)    # 'ca','es','fr','en'

    # Consentiment RGPD
    legal_document_id = Column(UUID(as_uuid=True), ForeignKey("legal_documents.id"))
    legal_document    = relationship("LegalDocument", back_populates="visits")
    accepted_at       = Column(DateTime(timezone=True))    # timestamp exacte del submit

    # Metadades tècniques
    ip_address       = Column(INET)
    user_agent       = Column(Text)

    # Timestamps
    checked_in_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    checked_out_at   = Column(DateTime(timezone=True))
    checkout_method  = Column(String(10))  # 'qr' | 'pin' | 'manual'

    # Sortida
    exit_token       = Column(String(64), unique=True)   # token pel QR de sortida
    exit_pin         = Column(String(6))                 # PIN 6 dígits


class AdminUser(Base):
    """Usuaris del panell d'administració (recepcionistes, seguretat, admin)."""
    __tablename__ = "admin_users"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(200), unique=True, nullable=False)
    name          = Column(String(200), nullable=False)
    password_hash = Column(String(200), nullable=False)  # bcrypt
    role          = Column(String(20), default="receptionist")  # 'admin' | 'receptionist' | 'viewer'
    active        = Column(Boolean, default=True)
    last_login    = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
```

---

## Rutes i endpoints

### Flux del visitant (públic, sense autenticació)

```
GET  /                          → Redirigeix a /ca/ o detecta idioma del navegador
GET  /{lang}/                   → language.html  — selecció d'idioma
GET  /{lang}/register           → form.html      — formulari de registre
POST /{lang}/register           → Processa formulari, redirigeix a /{lang}/legal
GET  /{lang}/legal              → legal.html     — textos legals + checkboxes
POST /{lang}/legal              → Processa acceptació, crea Visit a BD, redirigeix a /{lang}/confirmation/{visit_id}
GET  /{lang}/confirmation/{id}  → confirmation.html — QR sortida + PIN (reset als KIOSK_RESET_SECONDS)
```

### Registre de sortida (públic)

```
GET  /checkout                  → scan.html      — pantalla escaneig QR o PIN
POST /checkout/qr               → Valida exit_token, registra sortida, redirigeix a /checkout/done
POST /checkout/pin              → Valida exit_pin, registra sortida, redirigeix a /checkout/done
GET  /checkout/done             → done.html      — "Sortida registrada, fins aviat"
GET  /checkout/{exit_token}     → Accés directe via URL del QR, registra sortida
```

### Panell d'administració (requereix JWT en cookie)

```
GET  /admin/login               → login.html
POST /admin/login               → Valida credencials, genera JWT cookie, redirigeix a /admin/
GET  /admin/logout              → Elimina cookie, redirigeix a /admin/login

GET  /admin/                    → dashboard.html  — visites actives en temps real
GET  /admin/visits              → visits.html     — historial amb filtres
GET  /admin/visits/{id}         → visit_detail.html
POST /admin/visits/{id}/checkout → Registra sortida manual
GET  /admin/visits/export       → Retorna fitxer Excel (paràmetres: from, to, format=xlsx|csv)

GET  /admin/departments         → departments.html — CRUD departaments
POST /admin/departments         → Crea departament
PUT  /admin/departments/{id}    → Actualitza departament
DELETE /admin/departments/{id}  → Desactiva departament (soft delete)

GET  /admin/legal               → legal_docs.html — gestió textos legals
POST /admin/legal               → Crea nova versió (i desactiva l'anterior)
POST /admin/legal/{id}/activate → Activa aquesta versió

GET  /admin/users               → users.html (només rol 'admin')
POST /admin/users               → Crea usuari admin
PUT  /admin/users/{id}          → Actualitza usuari
POST /admin/users/{id}/reset-password → Reset contrasenya

# API JSON per HTMX (retornen JSON o HTML parcial)
GET  /admin/api/active-visits   → JSON: llista visites actives ara
GET  /admin/api/stats           → JSON: comptadors del dia
```

---

## Servei de traduccions (`app/services/i18n.py`)

### Estructura dels fitxers JSON

```json
{
  "lang_selector_title": "Seleccioneu l'idioma",
  "btn_catala": "Català",
  "btn_castella": "Castellano",
  "btn_frances": "Français",
  "btn_angles": "English",

  "form_title": "Registre de visita",
  "field_first_name": "Nom",
  "field_last_name": "Cognoms",
  "field_company": "Empresa / Organització",
  "field_id_document": "DNI / NIE / Passaport",
  "field_department": "Departament a visitar",
  "field_visit_reason": "Motiu de la visita",
  "field_phone": "Telèfon de contacte (opcional)",
  "field_required": "Camp obligatori",
  "btn_next": "Següent",
  "btn_back": "Tornar",
  "btn_submit": "Confirmar registre",

  "legal_title": "Informació i acceptació",
  "legal_scroll_hint": "Desplaceu-vos fins al final per continuar",
  "legal_check_rules": "He llegit i accepto les normes d'accés i seguretat.",
  "legal_check_rgpd": "Autoritzo el tractament de les meves dades per a la gestió d'accés a les instal·lacions.",
  "legal_both_required": "Heu d'acceptar tots dos punts per continuar.",

  "confirmation_title": "Registre completat",
  "confirmation_welcome": "Benvingut/da, {name}",
  "confirmation_checkin_time": "Entrada registrada a les {time}",
  "confirmation_exit_qr": "Codi per a la sortida",
  "confirmation_exit_pin": "O introduïu el PIN: {pin}",
  "confirmation_reset_msg": "Aquesta pantalla es reiniciarà en {secs} segons",

  "checkout_title": "Registre de sortida",
  "checkout_scan_qr": "Escanegeu el vostre codi QR",
  "checkout_or_pin": "O introduïu el vostre PIN",
  "checkout_pin_placeholder": "Codi de 6 dígits",
  "checkout_btn": "Registrar sortida",
  "checkout_done_title": "Sortida registrada",
  "checkout_done_msg": "Gràcies per la vostra visita. Fins aviat!",
  "checkout_not_found": "Codi no trobat o ja utilitzat.",

  "error_required": "Aquest camp és obligatori.",
  "error_invalid": "Format no vàlid.",
  "error_generic": "S'ha produït un error. Torneu-ho a intentar."
}
```

### Ús a les plantilles Jinja2

```python
# app/services/i18n.py
import json
from pathlib import Path
from functools import lru_cache

SUPPORTED_LANGS = ['ca', 'es', 'fr', 'en']
DEFAULT_LANG = 'ca'

@lru_cache(maxsize=4)
def load_translations(lang: str) -> dict:
    path = Path(f"translations/{lang}.json")
    if not path.exists():
        path = Path(f"translations/{DEFAULT_LANG}.json")
    return json.loads(path.read_text(encoding="utf-8"))

def t(lang: str, key: str, **kwargs) -> str:
    """Retorna la traducció i aplica format si cal."""
    translations = load_translations(lang)
    text = translations.get(key, key)  # fallback: retorna la clau
    return text.format(**kwargs) if kwargs else text
```

```jinja2
{# A les plantilles, la funció t() es passa al context #}
<h1>{{ t('form_title') }}</h1>
<label>{{ t('field_first_name') }} <span class="text-red-500">*</span></label>
```

---

## Servei de xifrat (`app/services/crypto.py`)

```python
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings

def _get_key() -> bytes:
    return base64.b64decode(settings.ENCRYPTION_KEY)

def encrypt(plaintext: str) -> tuple[bytes, bytes]:
    """Retorna (ciphertext, iv). Guardar tots dos a la BD."""
    key = _get_key()
    iv = os.urandom(12)             # 96 bits, únic per cada registre
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode(), None)
    return ciphertext, iv

def decrypt(ciphertext: bytes, iv: bytes) -> str:
    """Desxifra i retorna el text pla. Llança excepció si la clau és incorrecta."""
    key = _get_key()
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, None).decode()
```

**Important**: Mai registrar ni mostrar el DNI en logs. El desxifrat només es fa si un admin el sol·licita explícitament a `visit_detail.html`, i s'ha de quedar un log d'auditoria quan es fa.

---

## Servei de QR (`app/services/qr.py`)

```python
import qrcode
import io
import base64
from app.config import settings

def generate_qr_base64(data: str) -> str:
    """Genera un QR i el retorna com a string base64 per incrustar a l'HTML."""
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

def exit_url(exit_token: str) -> str:
    """URL completa que codifica el QR de sortida."""
    return f"{settings.BASE_URL}/checkout/{exit_token}"
```

---

## Lògica del flux del visitant (`app/routers/visitor.py`)

### POST /{lang}/legal — punt crític de creació del registre

```python
@router.post("/{lang}/legal")
async def submit_legal(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    form = await request.form()

    # 1. Validar que tots dos checkboxes estan marcats
    if not form.get("check_rules") or not form.get("check_rgpd"):
        # Tornar al formulari legal amb error
        ...

    # 2. Recuperar dades de la sessió (guardades al POST /register)
    session_data = request.session.get("visit_draft")
    if not session_data:
        return RedirectResponse(f"/{lang}/")

    # 3. Xifrar el DNI
    enc, iv = encrypt(session_data["id_document"])

    # 4. Obtenir document legal actiu
    legal_doc = await db.execute(
        select(LegalDocument).where(LegalDocument.active == True)
    )

    # 5. Generar exit_token i exit_pin únics
    exit_token = secrets.token_urlsafe(32)
    exit_pin   = f"{secrets.randbelow(1_000_000):06d}"

    # 6. Crear registre a la BD
    visit = Visit(
        location_id      = session_data["location_id"],
        first_name       = session_data["first_name"],
        last_name        = session_data["last_name"],
        company          = session_data["company"],
        id_document_enc  = enc,
        id_document_iv   = iv,
        phone            = session_data.get("phone"),
        department_id    = session_data["department_id"],
        visit_reason     = session_data["visit_reason"],
        language         = lang,
        legal_document_id = legal_doc.id,
        accepted_at      = datetime.utcnow(),
        ip_address       = request.client.host,
        user_agent       = request.headers.get("user-agent"),
        exit_token       = exit_token,
        exit_pin         = exit_pin,
    )
    db.add(visit)
    await db.commit()

    # 7. Netejar sessió i redirigir a confirmació
    request.session.pop("visit_draft", None)
    return RedirectResponse(f"/{lang}/confirmation/{visit.id}")
```

---

## Plantilles — comportament i UX

### `visitor/language.html`
- Quatre botons molt grans (mínim 80px alçada), un per idioma, icona de bandera SVG
- Fons net, logo de l'empresa a dalt
- Cap altra opció ni navegació visible (mode quiosc)

### `visitor/form.html`
- Camps en ordre vertical, tipus `input` grans per a pantalla tàctil (mínim 48px alçada)
- Teclat virtual del dispositiu s'obre automàticament al primer camp (`autofocus`)
- Validació client-side HTML5 (`required`, `maxlength`) + validació server-side
- Botó "Tornar" porta a selecció d'idioma. Botó "Següent" submeta el formulari
- Guardar dades a la sessió del servidor (no a localStorage)
- Si hi ha errors de validació: mostrar-los en vermell sota cada camp

### `visitor/legal.html`
- Contenidor de scroll per als textos legals, alçada màxima `60vh`
- **Important UX**: els botons de checkbox estan desactivats (`disabled`) fins que l'usuari fa scroll fins al final del text. Quan arriba al final, s'activen automàticament (HTMX o JS pur)
- Indicador visual de progrés de scroll ("↓ Continueu llegint")
- Els dos checkboxes han de ser marcats per poder continuar

### `visitor/confirmation.html`
- Missatge de benvinguda amb nom del visitant
- QR generat com `<img src="data:image/png;base64,{qr_b64}">`
- PIN de 6 dígits en format gran i llegible
- Compte enrere visible: "Aquesta pantalla es reiniciarà en X segons"
- JavaScript: `setTimeout(() => { window.location.href = '/{lang}/'; }, KIOSK_RESET_SECONDS * 1000)`
- El visitant pot clicar "Registrar sortida ara" si ja marxa al moment

### `checkout/scan.html`
- Dues opcions visuals:
  1. Instrucció per escanejar el QR (l'URL del QR redirigeix directament aquí)
  2. Camp per introduir el PIN manualment
- Disseny net, ús en tablet o mòbil

### `admin/dashboard.html`
- Taula de visites actives (checked_in_at ≠ null, checked_out_at = null)
- Columnes: Nom, Empresa, Departament, Hora entrada, Temps a instal·lacions, Accions
- Actualització automàtica cada 30 segons via HTMX (`hx-trigger="every 30s"`)
- Botó "Registrar sortida" per a cada fila (POST HTMX, actualitza la fila)
- Comptadors del dia: entrades, sortides, visites actives ara

### `admin/visits.html`
- Filtre per dates (from/to), empresa, departament, text lliure
- Paginació de 25 en 25
- Botó d'exportació Excel visible
- Cada fila té link a `visit_detail.html`

---

## Panell d'administració — Visualització i llistats

Aquesta és una funcionalitat crítica. El personal intern ha de poder consultar tots els registres, filtrar-los, veure estadístiques i exportar dades per a auditories o informes. Tot accessible des del navegador, sense necessitat de cap eina externa.

### Accés i rols

| Rol | Pot fer |
|---|---|
| `admin` | Tot: visites, configuració, usuaris, textos legals, estadístiques, exportació |
| `receptionist` | Veure visites actives, historial, registrar sortides manuals, exportar |
| `viewer` | Només consulta en mode lectura (historial i estadístiques, sense exportació) |

URL d'accés: `http://visites.empresa.local/admin`

---

### Vista 1: Dashboard en temps real (`admin/dashboard.html`)

**Objectiu**: Saber en tot moment qui hi ha a les instal·lacions.

**Targetes de resum (part superior)**:
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Visites actives │  │ Entrades avui   │  │ Sortides avui   │  │ Mitjana durada  │
│      (ara)      │  │    (total)      │  │    (total)      │  │   visita avui   │
│       12        │  │      47         │  │      35         │  │    1h 23min     │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Taula de visites actives**:

| # | Nom i cognoms | Empresa | Departament | Entrada | Temps dins | Accions |
|---|---|---|---|---|---|---|
| 1 | Joan García López | Ascensors Otis | Manteniment | 09:32 | 1h 47min | [Sortida manual] |
| 2 | Marie Dupont | Transportes SA | Logística | 10:15 | 1h 04min | [Sortida manual] |

- Fila en **groc** si porta més de 4 hores (configurable via `MAX_VISIT_HOURS` a `.env`)
- Fila en **vermell** si porta més de 8 hores
- Botó "Sortida manual" fa un POST HTMX i actualitza la fila sense recarregar la pàgina
- Actualització automàtica de la taula cada 30 s: `hx-get="/admin/api/active-visits" hx-trigger="every 30s" hx-target="#active-table"`

**Query SQL per a visites actives**:
```sql
SELECT v.id, v.first_name, v.last_name, v.company,
       d.name_ca AS department,
       v.checked_in_at,
       EXTRACT(EPOCH FROM (NOW() - v.checked_in_at))/60 AS minutes_inside
FROM visits v
LEFT JOIN departments d ON v.department_id = d.id
WHERE v.checked_out_at IS NULL
ORDER BY v.checked_in_at ASC;
```

---

### Vista 2: Historial de visites (`admin/visits.html`)

**Objectiu**: Consultar qualsevol visita passada amb filtres potents.

**Filtres disponibles** (tots opcionals, combinables):

```
┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ ┌──────────────────┐
│ Data des de  │ │ Data fins a  │ │ Empresa (text)     │ │ Departament      │
│ [2024-01-01] │ │ [2024-12-31] │ │ [_______________]  │ │ [Tots ▼]         │
└──────────────┘ └──────────────┘ └────────────────────┘ └──────────────────┘
┌──────────────────────────────┐  ┌─────────────┐  ┌──────────────────────────┐
│ Nom / cognoms (text lliure)  │  │ Estat       │  │ [Cercar]  [Netejar] [⬇ Excel] │
│ [__________________________] │  │ [Tots ▼]   │  └──────────────────────────┘
└──────────────────────────────┘  └─────────────┘
  (Tots | Actives | Completades)
```

**Columnes de la taula de resultats**:

| Nom i cognoms | Empresa | Departament | Entrada | Sortida | Durada | Estat | Accions |
|---|---|---|---|---|---|---|---|
| Joan García | Otis | Manteniment | 12/01 09:32 | 12/01 11:45 | 2h 13min | Completada | [Veure] |
| Marie Dupont | Transport SA | Logística | 12/01 10:15 | — | Activa | En curs | [Veure] [Sortida] |

- Paginació de 25 registres per pàgina, amb indicador "Mostrant 1-25 de 347 resultats"
- Ordena per qualsevol columna (clic a la capçalera)
- Estat "En curs" en verd, "Completada" en gris
- El botó [⬇ Excel] exporta **exactament els registres filtrats** (no tots), respectant els mateixos filtres

**Query SQL base per al llistat** (paràmetres opcionals):
```sql
SELECT v.id, v.first_name, v.last_name, v.company,
       d.name_ca AS department,
       v.checked_in_at, v.checked_out_at,
       CASE
         WHEN v.checked_out_at IS NOT NULL
         THEN EXTRACT(EPOCH FROM (v.checked_out_at - v.checked_in_at))/60
         ELSE NULL
       END AS duration_minutes,
       v.visit_reason, v.language, v.checkout_method
FROM visits v
LEFT JOIN departments d ON v.department_id = d.id
WHERE
    (:date_from  IS NULL OR v.checked_in_at >= :date_from)
    AND (:date_to    IS NULL OR v.checked_in_at <= :date_to + INTERVAL '1 day')
    AND (:company    IS NULL OR v.company ILIKE '%' || :company || '%')
    AND (:dept_id    IS NULL OR v.department_id = :dept_id)
    AND (:name       IS NULL OR (v.first_name || ' ' || v.last_name) ILIKE '%' || :name || '%')
    AND (:status     IS NULL
         OR (:status = 'active'    AND v.checked_out_at IS NULL)
         OR (:status = 'completed' AND v.checked_out_at IS NOT NULL))
ORDER BY v.checked_in_at DESC
LIMIT :limit OFFSET :offset;
```

---

### Vista 3: Detall d'una visita (`admin/visit_detail.html`)

**Objectiu**: Veure totes les dades d'un registre concret.

**Informació mostrada**:

```
Visita #a3f9...                                    [← Tornar al llistat]

DADES DEL VISITANT                    DADES DE LA VISITA
Nom:         Joan García López         Entrada:     12/01/2025 a les 09:32:14
Empresa:     Ascensors Otis SA         Sortida:     12/01/2025 a les 11:45:32
Telèfon:     +34 666 123 456           Durada:      2 hores 13 minuts
Idioma:      Català                    Departament: Manteniment
                                       Motiu:       Manteniment preventiu ascensor nº3

ACCEPTACIÓ RGPD
Document:    Versió 2024-09-01  [Veure document]
Acceptat a:  12/01/2025 09:31:47 UTC
IP:          192.168.1.45
Mètode sort: QR personal

DOCUMENT D'IDENTITAT
DNI/Passaport: [Veure DNI ⚠]    ← botó que desxifra sota demanda (confirmar mot de pas)

ACCIONS
[Registrar sortida manual]  [Eliminar registre]   ← eliminar = dret supressió RGPD
```

**Comportament del botó "Veure DNI"**:
- Demana confirmació: "Esteu segur? Aquesta acció quedarà registrada."
- Requereix que l'admin introdueixi la seva contrasenya per confirmar
- Desxifra el DNI i el mostra per 10 segons, llavors s'amaga automàticament
- Guarda a un log d'auditoria: `audit_log` (user_id, visit_id, action='view_id_document', timestamp, ip)

---

### Vista 4: Estadístiques (`admin/stats.html`)

**Objectiu**: Tendències i resum de períodes per a informes interns.

**Filtres**: Rang de dates (per defecte: mes actual)

**Blocs d'estadístiques**:

```
RESUM DEL PERÍODE (01/01/2025 – 31/01/2025)
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Total    │ │ Visitants│ │ Empreses │ │ Durada   │ │ Sense    │
│ visites  │ │ únics    │ │ úniques  │ │ mitjana  │ │ sortida  │
│   312    │ │   287    │ │    43    │ │ 1h 52min │ │    5     │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**Gràfic 1 — Visites per dia** (gràfic de barres, Chart.js via CDN):
- Eix X: dies del període
- Eix Y: nombre de visites
- Permet detectar pics d'afluència

**Gràfic 2 — Visites per departament** (gràfic de pastís):
- Proporció de visites a cada departament
- Útil per veure quins departaments reben més visites externes

**Gràfic 3 — Visites per franja horària** (gràfic de barres, agrupat per hora):
- De 07:00 a 20:00, agrupat per hora
- Permet planificar la cobertura de recepció

**Taula — Top empreses visitants**:
| Empresa | Visites | Última visita |
|---|---|---|
| Ascensors Otis SA | 24 | 15/01/2025 |
| Transportes García | 18 | 14/01/2025 |

**Query per estadístiques diàries**:
```sql
SELECT DATE(checked_in_at) AS day,
       COUNT(*) AS total,
       COUNT(DISTINCT company) AS companies,
       AVG(EXTRACT(EPOCH FROM (checked_out_at - checked_in_at))/60)
           FILTER (WHERE checked_out_at IS NOT NULL) AS avg_duration_min
FROM visits
WHERE checked_in_at BETWEEN :date_from AND :date_to
GROUP BY DATE(checked_in_at)
ORDER BY day;
```

---

### Vista 5: Exportació (`app/services/export.py`)

**Formats disponibles**: Excel (.xlsx) i CSV (.csv)

**Comportament**:
- El botó d'exportació apareix a `visits.html` i a `stats.html`
- Exporta **exactament el que es veu** (filtres aplicats), no tota la BD
- Límit: màxim 10.000 registres per exportació (protecció de rendiment)
- El DNI **mai** s'inclou a l'exportació (ni xifrat ni en clar)

**Columnes exportades**:
```python
EXPORT_COLUMNS = [
    ("ID",              lambda v: str(v.id)),
    ("Nom",             lambda v: v.first_name),
    ("Cognoms",         lambda v: v.last_name),
    ("Empresa",         lambda v: v.company),
    ("Telèfon",         lambda v: v.phone or ""),
    ("Departament",     lambda v: v.department.name_ca if v.department else ""),
    ("Motiu visita",    lambda v: v.visit_reason),
    ("Idioma",          lambda v: v.language),
    ("Data entrada",    lambda v: v.checked_in_at.strftime("%d/%m/%Y %H:%M")),
    ("Data sortida",    lambda v: v.checked_out_at.strftime("%d/%m/%Y %H:%M") if v.checked_out_at else ""),
    ("Durada (min)",    lambda v: round((v.checked_out_at - v.checked_in_at).seconds / 60) if v.checked_out_at else ""),
    ("Mètode sortida",  lambda v: v.checkout_method or ""),
    ("RGPD acceptat",   lambda v: v.accepted_at.strftime("%d/%m/%Y %H:%M") if v.accepted_at else ""),
]
```

**Implementació Excel (`openpyxl`)**:
```python
# app/services/export.py
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import io

def visits_to_excel(visits: list, filename_date_range: str) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Visites"

    # Capçalera amb estil
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF")
    headers = [col[0] for col in EXPORT_COLUMNS]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Dades
    for row_idx, visit in enumerate(visits, 2):
        for col_idx, (_, extractor) in enumerate(EXPORT_COLUMNS, 1):
            ws.cell(row=row_idx, column=col_idx, value=extractor(visit))

    # Amplada automàtica de columnes
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
```

**Endpoint d'exportació**:
```python
@router.get("/admin/visits/export")
async def export_visits(
    date_from: date | None = None,
    date_to:   date | None = None,
    company:   str | None = None,
    dept_id:   str | None = None,
    fmt:       str = "xlsx",
    db:        AsyncSession = Depends(get_db),
    admin:     AdminUser = Depends(get_current_admin),
):
    visits = await get_filtered_visits(db, date_from, date_to, company, dept_id, limit=10000)

    if fmt == "csv":
        content = visits_to_csv(visits)
        media_type = "text/csv"
        filename = f"visites_{date_from}_{date_to}.csv"
    else:
        content = visits_to_excel(visits, f"{date_from}_{date_to}")
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"visites_{date_from}_{date_to}.xlsx"

    return Response(
        content=content.getvalue(),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
```

---

### Taules addicionals al model per a auditoria

```python
class AuditLog(Base):
    """Registre d'accions sensibles dels admins (consulta DNI, eliminació, etc.)."""
    __tablename__ = "audit_logs"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id   = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    visit_id   = Column(UUID(as_uuid=True), ForeignKey("visits.id"), nullable=True)
    action     = Column(String(50), nullable=False)  # 'view_id_document' | 'delete_visit' | 'manual_checkout'
    ip_address = Column(INET)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    detail     = Column(Text)  # informació addicional en JSON
```

---

### Plantilles admin addicionals al directori

```
app/templates/admin/
├── base_admin.html        # Layout base del panell (navbar, sidebar, footer)
├── login.html             # Formulari login
├── dashboard.html         # Visites actives en temps real
├── visits.html            # Historial amb filtres i paginació
├── visit_detail.html      # Detall complet d'una visita
├── stats.html             # Estadístiques i gràfics
├── export_confirm.html    # Confirmació abans d'exportar (mostra nº registres)
├── departments.html       # CRUD departaments
├── legal_docs.html        # Gestió textos legals (crear versió, activar)
└── users.html             # Gestió usuaris admin (només rol 'admin')
```

**`base_admin.html`** ha d'incloure:
- Navbar amb: logo empresa | "Registre de Visites" | usuari logat | [Tancar sessió]
- Menú lateral: Dashboard | Historial | Estadístiques | Departaments | Textos legals | Usuaris
- Indicador visual a "Dashboard" si hi ha visites actives: badge vermell amb el nombre
- Responsive: el sidebar col·lapsa a hamburger en pantalles estretes

---

## Autenticació del panell admin

Usar **JWT en cookie HttpOnly** (no localStorage):

```python
# app/dependencies.py
from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt

async def get_current_admin(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    if not access_token:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    # ... obtenir usuari de BD i retornar-lo
```

---

## Mode quiosc — consideracions específiques

- **Sessió del servidor**: Usar `starlette.middleware.sessions.SessionMiddleware` per guardar les dades del formulari entre passos. Configurar `session_cookie` com HttpOnly i SameSite=Strict.
- **Prevenció de scroll a l'historial del navegador**: A la confirmació, usar `history.replaceState()` per evitar que el visitant torni enrere i vegi dades del visitant anterior.
- **Reset automàtic**: L'únic JavaScript necessari a confirmation.html és el compte enrere i el redirect.
- **Pantalla sempre activa**: La tablet ha de tenir "No apagar pantalla" configurat a nivell SO. L'app no gestiona això.
- **Evitar zoom**: `<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">`

---

## Seguretat

- **CSRF**: FastAPI no inclou protecció CSRF per defecte. Afegir token CSRF als formularis HTML. Usar la llibreria `itsdangerous` o implementar-ho manualment amb un camp hidden + validació al POST.
- **Rate limiting**: Limitar el POST `/register` a màxim 10 peticions per IP per minut per evitar abús. Usar `slowapi` (wrapper de `limits` per FastAPI).
- **Headers de seguretat**: Configurar a Nginx: `X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Content-Security-Policy`.
- **DNI en logs**: Assegurar-se que el DNI (ni xifrat ni en clar) apareix als logs d'accés de Nginx. Excloure el cos del POST dels logs.
- **Connexions BD**: Usar connexió SSL a PostgreSQL si és possible, tot i que sigui localhost.
- **Contrasenyes admin**: Mínim 12 caràcters, hash bcrypt amb cost factor 12.

---

## Desplegament al servidor Ubuntu

### 1. Preparar entorn

```bash
sudo mkdir -p /opt/visites /var/log/visites
sudo chown www-data:www-data /var/log/visites

cd /opt/visites
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Base de dades

```bash
# Connectar com a superusuari PostgreSQL
sudo -u postgres psql <<EOF
CREATE USER visites_user WITH PASSWORD 'PASSWORD_SEGURA';
CREATE DATABASE visites_db OWNER visites_user;
GRANT ALL PRIVILEGES ON DATABASE visites_db TO visites_user;
EOF

# Executar migracions
cd /opt/visites && source venv/bin/activate
alembic upgrade head

# Crear primer admin
python scripts/create_admin.py --email admin@empresa.com
```

### 3. Servei systemd

Fitxer: `/etc/systemd/system/visites.service`

```ini
[Unit]
Description=Registre de Visites
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/opt/visites
EnvironmentFile=/opt/visites/.env
ExecStart=/opt/visites/venv/bin/gunicorn app.main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8001 \
    --timeout 30 \
    --access-logfile /var/log/visites/access.log \
    --error-logfile /var/log/visites/error.log
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable visites
sudo systemctl start visites
sudo systemctl status visites
```

### 4. Nginx

Afegir al fitxer de configuració Nginx existent (o nou fitxer a `sites-available`):

```nginx
server {
    listen 80;
    server_name visites.empresa.local;  # o IP interna

    # Logs sense capturar cos del POST (per no guardar DNI)
    access_log /var/log/nginx/visites_access.log;
    error_log  /var/log/nginx/visites_error.log;

    # Headers de seguretat
    add_header X-Frame-Options "DENY";
    add_header X-Content-Type-Options "nosniff";
    add_header Referrer-Policy "strict-origin";

    location /static/ {
        alias /opt/visites/static/;
        expires 30d;
    }

    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 30;
    }
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Cron per a neteja automàtica de dades (RGPD)

```bash
# Afegir al crontab de www-data
sudo crontab -u www-data -e

# Executar cada nit a les 3:00
0 3 * * * /opt/visites/venv/bin/python /opt/visites/scripts/purge_old_visits.py >> /var/log/visites/purge.log 2>&1
```

---

## Tests

### Estructura (`tests/conftest.py`)

```python
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.main import app
from app.db.database import Base, get_db

DATABASE_URL_TEST = "postgresql+asyncpg://visites_user:pw@localhost/visites_test"

@pytest.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(DATABASE_URL_TEST)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def client(db_engine):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

### Tests mínims a implementar

```python
# test_visitor_flow.py
- test_language_page_returns_200
- test_form_page_requires_language_param
- test_form_submission_validates_required_fields
- test_form_submission_saves_session
- test_legal_page_shows_active_document
- test_legal_submission_without_checkboxes_returns_error
- test_legal_submission_creates_visit_in_db
- test_legal_submission_encrypts_id_document
- test_confirmation_shows_qr_and_pin

# test_checkout.py
- test_checkout_via_valid_qr_token
- test_checkout_via_valid_pin
- test_checkout_invalid_token_returns_error
- test_checkout_already_used_token_returns_error
- test_manual_checkout_via_admin

# test_crypto.py
- test_encrypt_decrypt_roundtrip
- test_different_iv_each_encryption
- test_wrong_key_raises_exception

# test_admin.py
- test_admin_login_valid_credentials
- test_admin_login_invalid_credentials
- test_admin_dashboard_requires_auth
- test_active_visits_api_returns_json
- test_export_returns_xlsx_file
```

---

## Decisió de disseny: Sessions per a flux multipas

El formulari té 3 passos (formulari → legal → confirmació). Les dades s'han de passar entre passos. Usar **sessions del servidor** (`SessionMiddleware`) i NO cookies de client ni localStorage per evitar que el visitant anterior pugui accedir a dades si no hi ha reset:

```python
# app/main.py
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="visites_session",
    max_age=1800,        # 30 minuts (suficient per omplir el formulari)
    same_site="strict",
    https_only=False,    # True si s'usa HTTPS
    httponly=True,
)
```

---

## Consideracions RGPD implementades al codi

1. **Xifrat en repòs**: DNI xifrat AES-256-GCM. IV únic per registre. Clau en variable d'entorn.
2. **Minimització de dades**: No demanar res que no sigui necessari. Telèfon és opcional.
3. **Versió de documents**: Guardar `legal_document_id` a cada visita per poder demostrar quins textos va acceptar.
4. **Timestamp d'acceptació**: Guardar `accepted_at` amb precisió de microsegons.
5. **Purga automàtica**: Script `purge_old_visits.py` elimina visites amb `checked_in_at < now() - interval '2 years'`.
6. **Dret de supressió**: L'admin pot eliminar un registre concret des del panell (`DELETE /admin/visits/{id}`).
7. **Accés al DNI auditat**: Registrar a un log d'auditoria cada vegada que un admin desxifra un DNI.

---

## Preguntes obertes (a respondre abans de començar)

- [ ] Quina versió d'Ubuntu? (per confirmar versions de Python disponibles)
- [ ] Les apps Python existents usen FastAPI, Django o Flask? (per seguir el mateix patró)
- [ ] Nginx: teniu `sites-available` / `sites-enabled` o un fitxer `nginx.conf` monolític?
- [ ] La tablet és Android o iPad? (afecta les instruccions de mode quiosc)
- [ ] Cal notificació per email al departament quan arriba el visitant? (Fase 2 o MVP?)
- [ ] Quants departaments hi ha? (per la migració inicial de dades)
- [ ] Teniu servidor SMTP intern o useu un servei extern (SendGrid, etc.)?
- [ ] Cal HTTPS al servidor intern? (si la tablet es connecta per WiFi, HTTP és suficient a xarxa local)
- [ ] Nom de domini o IP interna per a l'aplicació? (per configurar Nginx i les URLs dels QR)
