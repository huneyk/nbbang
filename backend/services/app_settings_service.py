"""전역 애플리케이션 설정 (admin 관리).

Google API key, 한국수출입은행 API key 등 전체 사용자가 공유하는 키를
암호화하여 MongoDB의 ``app_settings`` 컬렉션에 저장한다.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from config import Config
from services.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

APP_SETTINGS_DOC_TYPE = 'global_admin_settings'
SENSITIVE_KEYS = ('google_api_key', 'koreaexim_api_key')


def _collection():
    from services.database import _get_db  # 지연 임포트로 순환 회피
    return _get_db().app_settings


def get_app_settings() -> Dict[str, Any]:
    """전역 admin 설정을 평문으로 반환.

    저장된 값이 없으면 환경 변수에서 폴백.
    """
    doc = _collection().find_one({'_type': APP_SETTINGS_DOC_TYPE}) or {}
    result: Dict[str, Any] = {}

    google_key = doc.get('google_api_key', '')
    if google_key:
        result['google_api_key'] = decrypt_value(google_key)
    else:
        result['google_api_key'] = Config.GOOGLE_API_KEY or ''

    koreaexim_key = doc.get('koreaexim_api_key', '')
    if koreaexim_key:
        result['koreaexim_api_key'] = decrypt_value(koreaexim_key)
    else:
        result['koreaexim_api_key'] = Config.KOREAEXIM_API_KEY or ''

    result['migrated_at'] = doc.get('migrated_at')
    result['updated_at'] = doc.get('updated_at')
    return result


def update_app_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """admin 키 갱신 후 마스킹된 상태 반환."""
    doc = _collection().find_one({'_type': APP_SETTINGS_DOC_TYPE}) or {}
    changed = False

    for key in SENSITIVE_KEYS:
        if key in updates:
            new_value = (updates[key] or '').strip()
            if not new_value:
                doc.pop(key, None)
            else:
                doc[key] = encrypt_value(new_value)
            changed = True

    if changed:
        doc['_type'] = APP_SETTINGS_DOC_TYPE
        doc['updated_at'] = datetime.utcnow().isoformat()
        _collection().replace_one(
            {'_type': APP_SETTINGS_DOC_TYPE}, doc, upsert=True,
        )
        logger.info('전역 admin 설정 업데이트됨')

    return get_masked_settings()


def get_masked_settings() -> Dict[str, Any]:
    """API 키 값은 노출하지 않고 설정 여부만 반환."""
    settings = get_app_settings()
    return {
        'google_api_key_set': bool(settings.get('google_api_key')),
        'koreaexim_api_key_set': bool(settings.get('koreaexim_api_key')),
        'updated_at': settings.get('updated_at'),
    }


def mark_migrated() -> None:
    _collection().update_one(
        {'_type': APP_SETTINGS_DOC_TYPE},
        {'$set': {'migrated_at': datetime.utcnow().isoformat(),
                  '_type': APP_SETTINGS_DOC_TYPE}},
        upsert=True,
    )


def is_migrated() -> bool:
    doc = _collection().find_one({'_type': APP_SETTINGS_DOC_TYPE}) or {}
    return bool(doc.get('migrated_at'))


def seed_keys_from_env_if_missing() -> None:
    """저장된 키가 없을 때 환경 변수 값으로 초기 시드."""
    doc = _collection().find_one({'_type': APP_SETTINGS_DOC_TYPE}) or {}
    updates: Dict[str, Any] = {}

    if not doc.get('google_api_key') and Config.GOOGLE_API_KEY:
        updates['google_api_key'] = Config.GOOGLE_API_KEY
    if not doc.get('koreaexim_api_key') and Config.KOREAEXIM_API_KEY:
        updates['koreaexim_api_key'] = Config.KOREAEXIM_API_KEY

    if updates:
        update_app_settings(updates)
        logger.info('환경 변수의 API 키를 app_settings에 시드함')
