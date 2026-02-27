import base64
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import HKDF
from Crypto.Hash import SHA256
from config import settings


def _get_master_key() -> bytes:
    return base64.b64decode(settings.VAULT_MASTER_KEY)


def derive_key(secret_id: str) -> bytes:
    """Derive a 32-byte AES key unique to this secret using HKDF-SHA256."""
    return HKDF(
        master=_get_master_key(),
        key_len=32,
        salt=None,
        hashmod=SHA256,
        context=secret_id.encode(),
    )


def encrypt(plaintext: str, secret_id: str) -> dict:
    key = derive_key(secret_id)
    iv = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
    return {
        "value": base64.b64encode(ciphertext).decode(),
        "iv": base64.b64encode(iv).decode(),
        "tag": base64.b64encode(tag).decode(),
        "encoding": "aes256-gcm-hkdf",
    }


def decrypt(encrypted: dict, secret_id: str) -> str:
    key = derive_key(secret_id)
    cipher = AES.new(
        key,
        AES.MODE_GCM,
        nonce=base64.b64decode(encrypted["iv"]),
    )
    return cipher.decrypt_and_verify(
        base64.b64decode(encrypted["value"]),
        base64.b64decode(encrypted["tag"]),
    ).decode()
