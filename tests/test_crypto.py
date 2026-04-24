import base64
import os
import pytest

# Configurar clau de test abans d'importar el mòdul
os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()

from app.services.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    plaintext = "12345678A"
    ciphertext, iv = encrypt(plaintext)
    result = decrypt(ciphertext, iv)
    assert result == plaintext


def test_different_iv_each_encryption():
    _, iv1 = encrypt("12345678A")
    _, iv2 = encrypt("12345678A")
    assert iv1 != iv2


def test_wrong_key_raises_exception():
    ciphertext, iv = encrypt("12345678A")

    # Canviar la clau
    original_key = os.environ["ENCRYPTION_KEY"]
    os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()

    # Netejar cache de settings
    from app.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(Exception):
        decrypt(ciphertext, iv)

    # Restaurar
    os.environ["ENCRYPTION_KEY"] = original_key
    get_settings.cache_clear()
