"""Tests del servei de xifrat AES-256-GCM."""
import pytest

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


def test_encrypt_returns_bytes():
    ciphertext, iv = encrypt("TEST")
    assert isinstance(ciphertext, bytes)
    assert isinstance(iv, bytes)
    assert len(iv) == 12  # 96 bits


def test_decrypt_preserves_case():
    original = "Ab12Cd34Ef"
    ciphertext, iv = encrypt(original)
    result = decrypt(ciphertext, iv)
    assert result == original


def test_wrong_iv_raises_exception():
    ciphertext, iv = encrypt("12345678A")
    wrong_iv = bytes([0] * 12)
    with pytest.raises(Exception):
        decrypt(ciphertext, wrong_iv)


def test_tampered_ciphertext_raises_exception():
    ciphertext, iv = encrypt("12345678A")
    tampered = bytes([b ^ 0xFF for b in ciphertext])
    with pytest.raises(Exception):
        decrypt(tampered, iv)
