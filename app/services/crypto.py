import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_key() -> bytes:
    return base64.b64decode(settings.ENCRYPTION_KEY)


def encrypt(plaintext: str) -> tuple[bytes, bytes]:
    """Retorna (ciphertext, iv). Guardar tots dos a la BD."""
    key = _get_key()
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode(), None)
    return ciphertext, iv


def decrypt(ciphertext: bytes, iv: bytes) -> str:
    """Desxifra i retorna el text pla."""
    key = _get_key()
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, None).decode()


def normalize_id_document(value: str) -> str:
    """Normalitza un document d'identitat per a comparacions consistents."""
    return (value or "").strip().upper().replace(" ", "")


def hash_id_document(value: str) -> str:
    """HMAC-SHA256 del document normalitzat amb el pebre de l'app.

    Permet cerca indexada sense desxifrar AES. Sense el pebre, un dump de la
    BD no permet correlacionar registres amb DNIs coneguts. Retorna un hex
    de 64 caràcters.
    """
    if settings.LOOKUP_PEPPER:
        pepper = base64.b64decode(settings.LOOKUP_PEPPER)
    else:
        # Fallback per a tests/dev sense pebre. config.py impedeix arribar
        # aquí en producció.
        pepper = b"dev-only-pepper-not-secure"
    normalized = normalize_id_document(value).encode()
    return hmac.new(pepper, normalized, hashlib.sha256).hexdigest()
