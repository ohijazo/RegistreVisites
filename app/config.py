import base64
import sys

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://visites_user:password@localhost/visites_db"
    ENCRYPTION_KEY: str = ""
    SECRET_KEY: str = "canvia-aquesta-clau-secreta"
    JWT_SECRET_KEY: str = ""
    LOOKUP_PEPPER: str = ""
    KIOSK_SHARED_SECRET: str = ""
    KIOSK_IP_ALLOWLIST: str = ""

    SESSION_HOURS: int = 8
    EXIT_TOKEN_HOURS: int = 8
    KIOSK_RESET_SECONDS: int = 60
    KIOSK_CONFIRM_SECONDS: int = 15
    MAX_VISIT_HOURS_WARN: int = 4
    MAX_VISIT_HOURS_ALERT: int = 8
    AUTO_CLOSE_AFTER_HOURS: int = 12  # tancament automàtic de visites obertes

    COMPANY_NAME: str = "La Meva Empresa"
    COMPANY_ADDRESS: str = ""
    COMPANY_EMAIL: str = "dpo@empresa.com"
    BASE_URL: str = "http://localhost:8001"

    # Backend d'enviament de mails: 'smtp' o 'graph_ms'.
    # 'graph_ms' usa Microsoft Graph API (recomanat per a M365 modern,
    # sobreviu a la deprecació de SMTP AUTH).
    EMAIL_BACKEND: str = "smtp"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "visites@empresa.com"

    # Microsoft Graph (M365) — només cal si EMAIL_BACKEND=graph_ms
    MS_TENANT_ID: str = ""
    MS_CLIENT_ID: str = ""
    MS_CLIENT_SECRET: str = ""
    MS_SENDER_EMAIL: str = ""  # bústia que envia, ex: coromina@agrienergia.com

    # Power Automate webhook — només cal si EMAIL_BACKEND=power_automate.
    # La URL la genera Power Automate quan crees un flux amb trigger
    # 'When an HTTP request is received'. El secret és opcional però
    # recomanat: el flux pot validar-lo al header X-Webhook-Secret per
    # evitar que algú que descobreixi la URL pugui disparar emails.
    POWER_AUTOMATE_WEBHOOK_URL: str = ""
    POWER_AUTOMATE_SECRET: str = ""

    # Destinataris per defecte de la notificació automàtica al crear
    # una visita prevista (separats per comes). Camp buit = sense
    # notificació automàtica per defecte.
    EXPECTED_NOTIFY_RECIPIENTS: str = ""

    # Vàlvula de seguretat per a entorns de prova: si està definida,
    # tots els mails de qualsevol funcionalitat es redirigeixen a
    # aquesta adreça en comptes dels destinataris originals. El cos
    # del missatge inclou els destinataris reals com a referència.
    # Deixar buit en producció.
    EMAIL_OVERRIDE_RECIPIENT: str = ""

    ENV: str = "development"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    s = Settings()

    # Validar clau de xifrat
    if not s.ENCRYPTION_KEY:
        print("ERROR: ENCRYPTION_KEY no configurada al .env")
        sys.exit(1)
    try:
        key = base64.b64decode(s.ENCRYPTION_KEY)
        if len(key) != 32:
            print("ERROR: ENCRYPTION_KEY ha de ser de 32 bytes (AES-256)")
            sys.exit(1)
    except Exception:
        print("ERROR: ENCRYPTION_KEY no és base64 vàlid")
        sys.exit(1)

    # Validar secret key
    if s.SECRET_KEY == "canvia-aquesta-clau-secreta" and s.ENV == "production":
        print("ERROR: SECRET_KEY per defecte en producció. Canvia-la al .env")
        sys.exit(1)

    # JWT_SECRET_KEY ha de ser diferent de SECRET_KEY en producció;
    # en desenvolupament hi ha fallback a SECRET_KEY per comoditat.
    if not s.JWT_SECRET_KEY:
        if s.ENV == "production":
            print("ERROR: JWT_SECRET_KEY no configurada en producció")
            sys.exit(1)
        s.JWT_SECRET_KEY = s.SECRET_KEY
    elif s.JWT_SECRET_KEY == s.SECRET_KEY and s.ENV == "production":
        print("ERROR: JWT_SECRET_KEY ha de ser diferent de SECRET_KEY en producció")
        sys.exit(1)

    # LOOKUP_PEPPER: obligatori en producció per evitar oràcles de DNI
    if not s.LOOKUP_PEPPER and s.ENV == "production":
        print("ERROR: LOOKUP_PEPPER no configurada en producció")
        sys.exit(1)

    # En producció, almenys un mecanisme d'autenticació de quiosc ha d'estar
    # configurat per protegir els endpoints de cerca i checkout per DNI.
    if (
        s.ENV == "production"
        and not s.KIOSK_IP_ALLOWLIST
        and not s.KIOSK_SHARED_SECRET
    ):
        print(
            "ERROR: Configura almenys KIOSK_IP_ALLOWLIST o KIOSK_SHARED_SECRET "
            "en producció"
        )
        sys.exit(1)

    return s


settings = get_settings()
