import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from config import Config

logger = logging.getLogger(__name__)

_fernet_instance = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        secret = Config.SECRET_KEY or 'dev-secret-key'
        key = hashlib.sha256(secret.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key)
        _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def is_encrypted(value: str) -> bool:
    if not value or len(value) < 10:
        return False
    return value.startswith('gAAAAAB')


def encrypt_value(value: str) -> str:
    if not value or is_encrypted(value):
        return value
    try:
        f = _get_fernet()
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"암호화 실패: {e}")
        return value


def decrypt_value(value: str) -> str:
    if not value or not is_encrypted(value):
        return value
    try:
        f = _get_fernet()
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        logger.warning("복호화 실패: 유효하지 않은 토큰 (SECRET_KEY 변경 가능성)")
        return value
    except Exception as e:
        logger.error(f"복호화 실패: {e}")
        return value
