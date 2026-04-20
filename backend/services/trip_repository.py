"""사용자 스코프 트립/경비 저장소.

각 트립은 ``trips`` 컬렉션의 단일 문서로 저장된다. 경비는 트립 문서에 임베드되며,
영수증 이미지는 GridFS의 ``receipt_image`` ID로만 참조된다.

스키마::

    {
        '_id': ObjectId,
        'trip_id': str,             # 짧은 사람-읽기 가능한 ID
        'user_id': str,             # 소유자
        'is_active': bool,          # 사용자별 1개의 active 트립
        'created_at': str (iso),
        'updated_at': str (iso),
        'settings': {
            'trip_title': str,
            'participants': [str],
            'categories': [str],
            'credit_card_fee_rate': float,   # (legacy) 트립에 저장된 수수료율. 현재는 사용자 프로필 값이 우선.
            'currencies': [...],
            'exchange_rates': {...},
            'exchange_rate_info': {...},
        },
        'expenses': [
            { 'id': str, 'date': str, 'category': str, 'amount': float,
              'currency': str, 'krw_amount': float, 'payment_method': str,
              'description': str, 'payer': str, 'receipt_image': str|None,
              'is_personal_expense': bool, 'personal_expense_for': str|None,
              'exchange_rate': float, 'created_at': str (iso) }, ...
        ]
    }
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import DESCENDING

logger = logging.getLogger(__name__)


DEFAULT_CURRENCIES = [
    {'code': 'KRW', 'name': '원', 'flag': '🇰🇷', 'rate': 1.0, 'is_base': True},
    {'code': 'USD', 'name': '달러', 'flag': '🇺🇸', 'rate': 1350.0, 'is_base': False},
    {'code': 'JPY', 'name': '엔', 'flag': '🇯🇵', 'rate': 9.5, 'is_base': False},
    {'code': 'CNY', 'name': '위안', 'flag': '🇨🇳', 'rate': 185.0, 'is_base': False},
    {'code': 'EUR', 'name': '유로', 'flag': '🇪🇺', 'rate': 1480.0, 'is_base': False},
    {'code': 'HKD', 'name': '홍콩달러', 'flag': '🇭🇰', 'rate': 173.0, 'is_base': False},
]

DEFAULT_CATEGORIES = ['교통비', '식사비', '음료/간식', '숙박비', '기타']


def _collection():
    from services.database import _get_db
    return _get_db().trips


def ensure_indexes() -> None:
    _collection().create_index([('user_id', 1), ('is_active', 1)])
    _collection().create_index('trip_id', unique=False)


def _serialize(doc: Optional[Dict]) -> Optional[Dict]:
    if not doc:
        return None
    doc = dict(doc)
    if isinstance(doc.get('_id'), ObjectId):
        doc['_id'] = str(doc['_id'])
    return doc


DEFAULT_CREDIT_CARD_FEE_RATE = 2.5


def _default_settings(trip_title: str = '여행 경비 정산',
                      participants: Optional[List[str]] = None,
                      categories: Optional[List[str]] = None,
                      credit_card_fee_rate: float = DEFAULT_CREDIT_CARD_FEE_RATE
                      ) -> Dict[str, Any]:
    currencies = [dict(c) for c in DEFAULT_CURRENCIES]
    return {
        'trip_title': trip_title,
        'participants': participants or [],
        'categories': categories or list(DEFAULT_CATEGORIES),
        'credit_card_fee_rate': credit_card_fee_rate,
        'currencies': currencies,
        'exchange_rates': {c['code']: c['rate'] for c in currencies},
        'exchange_rate_info': {'source': '', 'updated_at': '', 'rate_type': ''},
    }


def list_trips(user_id: str) -> List[Dict[str, Any]]:
    """사용자의 모든 트립 요약 목록 반환."""
    trips = []
    for doc in _collection().find({'user_id': user_id}).sort('created_at', DESCENDING):
        expenses = doc.get('expenses', [])
        trips.append({
            'id': doc.get('trip_id'),
            'title': doc.get('settings', {}).get('trip_title', '제목 없음'),
            'created_at': doc.get('created_at', ''),
            'updated_at': doc.get('updated_at', ''),
            'is_active': bool(doc.get('is_active')),
            'expense_count': len(expenses),
            'total_krw': sum(e.get('krw_amount', 0) for e in expenses),
        })
    return trips


def get_trip(user_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
    return _serialize(_collection().find_one({'user_id': user_id, 'trip_id': trip_id}))


def get_active_trip(user_id: str) -> Optional[Dict[str, Any]]:
    return _serialize(_collection().find_one({'user_id': user_id, 'is_active': True}))


def get_or_create_active_trip(user_id: str, default_title: str = '새 여행') -> Dict[str, Any]:
    active = get_active_trip(user_id)
    if active:
        return active
    return create_trip(user_id, default_title)


def _apply_latest_rates_to_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """신규 트립 settings에 최신 환율을 best-effort로 반영한다.

    외부 API 조회 실패 시에도 조용히 기본 환율로 폴백하여 트립 생성 자체는 막지 않는다.
    """
    try:
        from services.exchange_rate_service import fetch_exchange_rates, apply_fetched_rates
        result = fetch_exchange_rates(settings)
        if result.get('rates'):
            return apply_fetched_rates(settings, result)
        logger.warning('신규 트립 최신 환율 조회 실패: 기본 환율로 생성')
    except Exception as e:
        logger.warning(f'신규 트립 최신 환율 적용 실패: {e}. 기본 환율로 생성')
    return settings


def create_trip(user_id: str, trip_title: str,
                participants: Optional[List[str]] = None,
                categories: Optional[List[str]] = None,
                credit_card_fee_rate: float = 2.5,
                make_active: bool = True) -> Dict[str, Any]:
    """새 트립 생성. make_active=True이면 기존 active 트립을 비활성화한다.

    신규 트립은 생성 시점의 최신 환율을 자동으로 조회하여 '환율 설정'의 기본값으로 반영한다.
    """
    if make_active:
        _collection().update_many(
            {'user_id': user_id, 'is_active': True},
            {'$set': {'is_active': False}},
        )

    settings = _default_settings(
        trip_title=trip_title,
        participants=participants,
        categories=categories,
        credit_card_fee_rate=credit_card_fee_rate,
    )
    settings = _apply_latest_rates_to_settings(settings)

    now = datetime.utcnow().isoformat()
    doc = {
        'trip_id': str(uuid.uuid4())[:8],
        'user_id': user_id,
        'is_active': bool(make_active),
        'created_at': now,
        'updated_at': now,
        'settings': settings,
        'expenses': [],
    }
    result = _collection().insert_one(doc)
    doc['_id'] = str(result.inserted_id)
    return doc


def set_active_trip(user_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
    target = _collection().find_one({'user_id': user_id, 'trip_id': trip_id})
    if not target:
        return None
    _collection().update_many(
        {'user_id': user_id, 'is_active': True},
        {'$set': {'is_active': False}},
    )
    _collection().update_one(
        {'_id': target['_id']},
        {'$set': {'is_active': True, 'updated_at': datetime.utcnow().isoformat()}},
    )
    return get_active_trip(user_id)


def update_trip_settings(user_id: str, trip_id: str,
                         settings_patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """트립 settings 일부 업데이트. API 키 필드는 무시한다."""
    target = _collection().find_one({'user_id': user_id, 'trip_id': trip_id})
    if not target:
        return None

    settings = target.get('settings', {})
    for key, value in settings_patch.items():
        if key in ('google_api_key', 'koreaexim_api_key', '_id', '_type'):
            continue
        settings[key] = value

    _collection().update_one(
        {'_id': target['_id']},
        {'$set': {'settings': settings,
                  'updated_at': datetime.utcnow().isoformat()}},
    )
    return get_trip(user_id, trip_id)


def delete_trip(user_id: str, trip_id: str) -> bool:
    """트립 삭제. 영수증 GridFS도 정리한다."""
    target = _collection().find_one({'user_id': user_id, 'trip_id': trip_id})
    if not target:
        return False

    from services.receipt_storage import delete_receipt
    for exp in target.get('expenses', []):
        receipt_id = exp.get('receipt_image')
        if receipt_id:
            try:
                delete_receipt(receipt_id)
            except Exception:
                pass

    _collection().delete_one({'_id': target['_id']})

    if target.get('is_active'):
        remaining = _collection().find_one(
            {'user_id': user_id}, sort=[('created_at', DESCENDING)],
        )
        if remaining:
            _collection().update_one(
                {'_id': remaining['_id']}, {'$set': {'is_active': True}},
            )
    return True


# ===== 경비 (트립에 임베드) =====

def list_expenses(user_id: str) -> List[Dict[str, Any]]:
    trip = get_active_trip(user_id)
    if not trip:
        return []
    expenses = list(trip.get('expenses', []))
    expenses.sort(key=lambda e: e.get('created_at', ''), reverse=True)
    return expenses


def add_expense(user_id: str, expense: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    trip = get_active_trip(user_id)
    if not trip:
        trip = create_trip(user_id, '새 여행')

    expense = dict(expense)
    expense.setdefault('id', str(uuid.uuid4()))
    expense.setdefault('created_at', datetime.utcnow().isoformat())

    _collection().update_one(
        {'_id': ObjectId(trip['_id'])},
        {'$push': {'expenses': expense},
         '$set': {'updated_at': datetime.utcnow().isoformat()}},
    )
    return expense


def delete_expense(user_id: str, expense_id: str) -> bool:
    trip = get_active_trip(user_id)
    if not trip:
        return False

    target = next((e for e in trip.get('expenses', [])
                   if e.get('id') == expense_id or str(e.get('_id', '')) == expense_id), None)
    if not target:
        return False

    receipt_id = target.get('receipt_image')
    if receipt_id:
        from services.receipt_storage import delete_receipt
        try:
            delete_receipt(receipt_id)
        except Exception:
            pass

    _collection().update_one(
        {'_id': ObjectId(trip['_id'])},
        {'$pull': {'expenses': {'$or': [{'id': expense_id}, {'_id': expense_id}]}},
         '$set': {'updated_at': datetime.utcnow().isoformat()}},
    )
    return True


def get_active_settings(user_id: str) -> Dict[str, Any]:
    trip = get_active_trip(user_id)
    if not trip:
        return _default_settings()
    return trip.get('settings', _default_settings())


# ===== 관리자 집계 =====

def count_trips_all() -> int:
    return _collection().count_documents({})


def count_trips_by_user(user_id: str) -> int:
    return _collection().count_documents({'user_id': user_id})


def aggregate_global_stats() -> Dict[str, Any]:
    """전체 트립/경비 합계. {trip_count, expense_count, total_krw}."""
    pipeline = [
        {'$project': {
            'expense_count': {'$size': {'$ifNull': ['$expenses', []]}},
            'total_krw': {'$sum': '$expenses.krw_amount'},
        }},
        {'$group': {
            '_id': None,
            'trip_count': {'$sum': 1},
            'expense_count': {'$sum': '$expense_count'},
            'total_krw': {'$sum': '$total_krw'},
        }},
    ]
    result = list(_collection().aggregate(pipeline))
    if not result:
        return {'trip_count': 0, 'expense_count': 0, 'total_krw': 0.0}
    doc = result[0]
    return {
        'trip_count': int(doc.get('trip_count') or 0),
        'expense_count': int(doc.get('expense_count') or 0),
        'total_krw': float(doc.get('total_krw') or 0.0),
    }


def aggregate_stats_by_user(user_id: str) -> Dict[str, Any]:
    """사용자별 트립/경비 요약."""
    pipeline = [
        {'$match': {'user_id': user_id}},
        {'$project': {
            'expense_count': {'$size': {'$ifNull': ['$expenses', []]}},
            'total_krw': {'$sum': '$expenses.krw_amount'},
        }},
        {'$group': {
            '_id': None,
            'trip_count': {'$sum': 1},
            'expense_count': {'$sum': '$expense_count'},
            'total_krw': {'$sum': '$total_krw'},
        }},
    ]
    result = list(_collection().aggregate(pipeline))
    if not result:
        return {'trip_count': 0, 'expense_count': 0, 'total_krw': 0.0}
    doc = result[0]
    return {
        'trip_count': int(doc.get('trip_count') or 0),
        'expense_count': int(doc.get('expense_count') or 0),
        'total_krw': float(doc.get('total_krw') or 0.0),
    }


def delete_trips_by_user(user_id: str) -> int:
    """사용자의 모든 트립을 삭제. 영수증(GridFS)도 정리. 삭제된 트립 수 반환."""
    from services.receipt_storage import delete_receipt

    deleted = 0
    for doc in _collection().find({'user_id': user_id}):
        for exp in doc.get('expenses', []):
            receipt_id = exp.get('receipt_image')
            if receipt_id:
                try:
                    delete_receipt(receipt_id)
                except Exception:
                    pass
        _collection().delete_one({'_id': doc['_id']})
        deleted += 1
    return deleted


def save_active_settings(user_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    trip = get_active_trip(user_id)
    if not trip:
        trip = create_trip(user_id, settings.get('trip_title', '새 여행'))
    cleaned = {k: v for k, v in settings.items()
               if k not in ('google_api_key', 'koreaexim_api_key', '_id', '_type')}
    _collection().update_one(
        {'_id': ObjectId(trip['_id'])},
        {'$set': {'settings': cleaned,
                  'updated_at': datetime.utcnow().isoformat()}},
    )
    return cleaned
