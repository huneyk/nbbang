import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

import certifi
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from config import Config


_client: Optional[MongoClient] = None
_db = None

DEFAULT_SETTINGS = {
    'trip_id': None,
    'trip_title': '여행 경비 정산',
    'participants': ['참가자1', '참가자2'],
    'categories': ['교통비', '식사비', '음료/간식', '숙박비', '기타'],
    'credit_card_fee_rate': 2.5,
    'google_api_key': '',
    'currencies': [
        {'code': 'KRW', 'name': '원', 'flag': '🇰🇷', 'rate': 1.0, 'is_base': True},
        {'code': 'JPY', 'name': '엔', 'flag': '🇯🇵', 'rate': 9.5, 'is_base': False},
        {'code': 'USD', 'name': '달러', 'flag': '🇺🇸', 'rate': 1350.0, 'is_base': False}
    ],
    'exchange_rates': {
        'KRW': 1.0,
        'JPY': 9.5,
        'USD': 1350.0
    }
}


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(Config.MONGODB_URI, tlsCAFile=certifi.where())
    return _client


def _get_db():
    global _db
    if _db is None:
        _db = _get_client()[Config.DATABASE_NAME]
    return _db


def _serialize_doc(doc: Optional[Dict]) -> Optional[Dict]:
    """ObjectId를 문자열로 변환하여 JSON 직렬화 가능하게 만듦"""
    if doc is None:
        return None
    doc = dict(doc)
    if '_id' in doc and isinstance(doc['_id'], ObjectId):
        doc['_id'] = str(doc['_id'])
    return doc


# ===== 설정 관리 =====

def load_settings() -> Dict[str, Any]:
    """저장된 설정 로드"""
    db = _get_db()
    settings = db.settings.find_one({'_type': 'app_settings'})

    if settings is None:
        initial = DEFAULT_SETTINGS.copy()
        initial['_type'] = 'app_settings'
        db.settings.insert_one(initial)
        return DEFAULT_SETTINGS.copy()

    settings.pop('_id', None)
    settings.pop('_type', None)

    for key, value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = value

    return settings


def save_settings(settings: Dict[str, Any]):
    """설정 저장"""
    db = _get_db()
    update_data = {k: v for k, v in settings.items() if k not in ('_id', '_type')}
    update_data['_type'] = 'app_settings'
    db.settings.replace_one(
        {'_type': 'app_settings'},
        update_data,
        upsert=True
    )


# ===== 여행 관리 =====

def list_trips() -> List[Dict[str, Any]]:
    """저장된 모든 여행 목록 반환"""
    db = _get_db()
    trips = []

    for trip_data in db.trips.find().sort('archived_at', DESCENDING):
        trips.append({
            'id': trip_data.get('trip_id', str(trip_data.get('_id', ''))),
            'title': trip_data.get('settings', {}).get('trip_title', '제목 없음'),
            'created_at': trip_data.get('created_at', ''),
            'archived_at': trip_data.get('archived_at', ''),
            'expense_count': len(trip_data.get('expenses', [])),
            'total_krw': sum(exp.get('krw_amount', 0) for exp in trip_data.get('expenses', []))
        })

    return trips


def archive_current_trip() -> Optional[str]:
    """현재 여행을 아카이브하고 trip_id 반환"""
    settings = load_settings()
    expenses = load_expenses()

    if not expenses and settings.get('trip_title') == DEFAULT_SETTINGS['trip_title']:
        return None

    trip_id = str(uuid.uuid4())[:8]
    archived_at = datetime.now().isoformat()

    trip_data = {
        'trip_id': trip_id,
        'created_at': settings.get('created_at', archived_at),
        'archived_at': archived_at,
        'settings': settings,
        'expenses': expenses
    }

    db = _get_db()
    db.trips.insert_one(trip_data)

    return trip_id


def create_new_trip(new_title: str, participants: List[str] = None,
                    categories: List[str] = None, credit_card_fee_rate: float = 2.5) -> Dict[str, Any]:
    """새로운 여행 생성 (현재 데이터 초기화)"""
    new_settings = {
        'trip_id': None,
        'trip_title': new_title,
        'participants': participants or ['참가자1', '참가자2'],
        'categories': categories or ['교통비', '식사비', '음료/간식', '숙박비', '기타'],
        'credit_card_fee_rate': credit_card_fee_rate,
        'exchange_rates': DEFAULT_SETTINGS['exchange_rates'].copy(),
        'created_at': datetime.now().isoformat()
    }

    save_settings(new_settings)

    db = _get_db()
    db.expenses.delete_many({})

    return new_settings


def load_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    """아카이브된 여행 불러오기"""
    db = _get_db()
    trip_data = db.trips.find_one({'trip_id': trip_id})

    if not trip_data:
        return None

    settings = trip_data.get('settings', DEFAULT_SETTINGS.copy())
    settings['trip_id'] = trip_id
    expenses = trip_data.get('expenses', [])

    save_settings(settings)

    db.expenses.delete_many({})
    if expenses:
        for exp in expenses:
            exp.pop('_id', None)
        db.expenses.insert_many(expenses)

    reload_expenses = [_serialize_doc(e) for e in db.expenses.find()]

    return {
        'settings': settings,
        'expenses': reload_expenses
    }


def delete_trip(trip_id: str) -> bool:
    """아카이브된 여행 삭제"""
    db = _get_db()
    result = db.trips.delete_one({'trip_id': trip_id})
    return result.deleted_count > 0


def load_expenses() -> List[Dict[str, Any]]:
    """저장된 경비 데이터 로드"""
    db = _get_db()
    return [_serialize_doc(exp) for exp in db.expenses.find()]


def save_expenses(expenses: List[Dict[str, Any]]):
    """경비 데이터 저장 (전체 교체)"""
    db = _get_db()
    db.expenses.delete_many({})
    if expenses:
        for exp in expenses:
            exp.pop('_id', None)
        db.expenses.insert_many(expenses)


# ===== Database wrapper (routes에서 사용하는 API 유지) =====

class MongoExpenseCollection:
    """pymongo 컬렉션을 감싸서 _id 직렬화를 자동 처리"""

    def __init__(self):
        self._collection = _get_db().expenses

    def find(self, filter_dict: Optional[Dict] = None):
        if filter_dict and '_id' in filter_dict:
            filter_dict = filter_dict.copy()
            try:
                filter_dict['_id'] = ObjectId(filter_dict['_id'])
            except Exception:
                pass
        cursor = self._collection.find(filter_dict or {})
        return SerializableCursor(cursor)

    def insert_one(self, document: Dict) -> 'InsertResult':
        doc = document.copy()
        doc.pop('_id', None)
        doc['created_at'] = datetime.utcnow().isoformat()
        result = self._collection.insert_one(doc)
        return InsertResult(str(result.inserted_id))

    def delete_one(self, filter_dict: Dict) -> 'DeleteResult':
        if '_id' in filter_dict:
            filter_dict = filter_dict.copy()
            try:
                filter_dict['_id'] = ObjectId(filter_dict['_id'])
            except Exception:
                pass
        result = self._collection.delete_one(filter_dict)
        return DeleteResult(result.deleted_count)


class SerializableCursor:
    """pymongo 커서를 감싸서 _id를 문자열로 자동 변환"""

    def __init__(self, cursor):
        self._cursor = cursor

    def sort(self, field: str, direction: int = -1):
        self._cursor = self._cursor.sort(field, direction)
        return self

    def __iter__(self):
        for doc in self._cursor:
            yield _serialize_doc(doc)


class InsertResult:
    def __init__(self, inserted_id: str):
        self.inserted_id = inserted_id


class DeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class MongoDatabase:
    """routes에서 get_database().expenses 형태로 접근"""

    @property
    def expenses(self):
        return MongoExpenseCollection()


def get_database() -> MongoDatabase:
    """데이터베이스 인스턴스 반환"""
    return MongoDatabase()


def close_connection():
    """MongoDB 연결 종료"""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
