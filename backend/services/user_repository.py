"""사용자 컬렉션 CRUD."""
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

DEFAULT_CREDIT_CARD_FEE_RATE = 0.0


def _coerce_fee_rate(value: Any,
                     fallback: float = DEFAULT_CREDIT_CARD_FEE_RATE) -> float:
    """입력값을 0~100 사이의 float 수수료율(%)로 변환. 실패하면 fallback."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if rate < 0:
        return 0.0
    if rate > 100:
        return 100.0
    return rate


def _collection():
    from services.database import _get_db
    return _get_db().users


def _serialize(user: Optional[Dict]) -> Optional[Dict]:
    """API에 노출할 사용자 dict. password_hash는 제거하고 has_password 플래그로 대체."""
    if not user:
        return None
    user = dict(user)
    if isinstance(user.get('_id'), ObjectId):
        user['_id'] = str(user['_id'])
    user['id'] = user['_id']
    user['has_password'] = bool(user.get('password_hash'))
    user['credit_card_fee_rate'] = _coerce_fee_rate(
        user.get('credit_card_fee_rate'), DEFAULT_CREDIT_CARD_FEE_RATE,
    )
    user.pop('password_hash', None)
    return user


def ensure_indexes() -> None:
    _collection().create_index('email', unique=True)


def find_by_email(email: str) -> Optional[Dict[str, Any]]:
    user = _collection().find_one({'email': email.strip().lower()})
    return _serialize(user)


def find_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
    return _serialize(_collection().find_one({'_id': oid}))


def find_password_hash(user_id: str) -> Optional[str]:
    """내부용: 비밀번호 검증을 위해 password_hash만 조회."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
    doc = _collection().find_one({'_id': oid}, {'password_hash': 1})
    if not doc:
        return None
    return doc.get('password_hash')


def find_password_hash_by_email(email: str) -> Optional[str]:
    doc = _collection().find_one(
        {'email': email.strip().lower()}, {'password_hash': 1},
    )
    if not doc:
        return None
    return doc.get('password_hash')


def create_user(email: str, name: str = '', is_admin: bool = False,
                password_hash: str = '') -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    doc = {
        'email': email.strip().lower(),
        'name': (name or '').strip() or email.split('@')[0],
        'is_admin': bool(is_admin),
        'created_at': now,
        'last_login_at': now,
    }
    if password_hash:
        doc['password_hash'] = password_hash
    result = _collection().insert_one(doc)
    doc['_id'] = str(result.inserted_id)
    return _serialize(doc)


def set_password_hash(user_id: str, password_hash: str) -> bool:
    try:
        oid = ObjectId(user_id)
    except Exception:
        return False
    result = _collection().update_one(
        {'_id': oid},
        {'$set': {
            'password_hash': password_hash,
            'password_updated_at': datetime.utcnow().isoformat(),
        }},
    )
    return result.matched_count > 0


def touch_login(user_id: str) -> None:
    try:
        oid = ObjectId(user_id)
    except Exception:
        return
    _collection().update_one(
        {'_id': oid},
        {'$set': {'last_login_at': datetime.utcnow().isoformat()}},
    )


def list_users() -> list:
    return [_serialize(u) for u in _collection().find().sort('created_at', -1)]


def update_user(user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """허용된 필드만 갱신 후 업데이트된 문서를 반환."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None

    allowed = {}
    if 'is_admin' in updates:
        allowed['is_admin'] = bool(updates['is_admin'])
    if 'name' in updates:
        name = (updates.get('name') or '').strip()
        if name:
            allowed['name'] = name
    if 'credit_card_fee_rate' in updates:
        allowed['credit_card_fee_rate'] = _coerce_fee_rate(
            updates['credit_card_fee_rate'],
        )
    if not allowed:
        return find_by_id(user_id)

    result = _collection().update_one({'_id': oid}, {'$set': allowed})
    if result.matched_count == 0:
        return None
    return find_by_id(user_id)


def delete_user(user_id: str) -> bool:
    try:
        oid = ObjectId(user_id)
    except Exception:
        return False
    return _collection().delete_one({'_id': oid}).deleted_count > 0


def get_credit_card_fee_rate(user_id: str) -> float:
    """사용자의 신용카드 수수료율(%)을 반환. 없으면 기본값."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        return DEFAULT_CREDIT_CARD_FEE_RATE
    doc = _collection().find_one({'_id': oid}, {'credit_card_fee_rate': 1})
    if not doc:
        return DEFAULT_CREDIT_CARD_FEE_RATE
    return _coerce_fee_rate(doc.get('credit_card_fee_rate'))


def set_credit_card_fee_rate(user_id: str, rate: Any) -> Optional[float]:
    """사용자의 신용카드 수수료율을 갱신하고 저장된 값을 반환."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
    value = _coerce_fee_rate(rate)
    result = _collection().update_one(
        {'_id': oid},
        {'$set': {'credit_card_fee_rate': value}},
    )
    if result.matched_count == 0:
        return None
    return value


def count_users() -> int:
    return _collection().count_documents({})


def count_admins() -> int:
    return _collection().count_documents({'is_admin': True})


def count_recent_logins(since_iso: str) -> int:
    """since_iso 이후에 last_login_at이 기록된 사용자 수."""
    return _collection().count_documents({'last_login_at': {'$gte': since_iso}})


def count_recent_signups(since_iso: str) -> int:
    return _collection().count_documents({'created_at': {'$gte': since_iso}})


def clear_password(user_id: str) -> bool:
    """관리자용: 사용자의 비밀번호를 강제로 제거 (코드 기반 재설정을 유도)."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        return False
    result = _collection().update_one(
        {'_id': oid},
        {'$unset': {'password_hash': ''},
         '$set': {'password_updated_at': datetime.utcnow().isoformat()}},
    )
    return result.matched_count > 0
