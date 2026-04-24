import base64
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
