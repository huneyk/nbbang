import json
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from config import Config


# JSON 파일 기반 간단한 데이터베이스
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
TRIPS_DIR = os.path.join(DATA_DIR, 'trips')  # 아카이브된 여행 저장 폴더
DATA_FILE = os.path.join(DATA_DIR, 'expenses.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')

# 기본 설정값
DEFAULT_SETTINGS = {
    'trip_id': None,  # 현재 여행 ID (새 여행이면 None)
    'trip_title': '여행 경비 정산',
    'participants': ['참가자1', '참가자2'],
    'categories': ['교통비', '식사비', '음료/간식', '숙박비', '기타'],
    'credit_card_fee_rate': 2.5,  # 퍼센트 단위
    'openai_api_key': '',  # OpenAI API 키
    'currencies': [
        {'code': 'KRW', 'name': '원', 'flag': '🇰🇷', 'rate': 1.0, 'is_base': True},
        {'code': 'JPY', 'name': '엔', 'flag': '🇯🇵', 'rate': 9.5, 'is_base': False},
        {'code': 'USD', 'name': '달러', 'flag': '🇺🇸', 'rate': 1350.0, 'is_base': False}
    ],
    # 하위 호환성을 위해 exchange_rates도 유지
    'exchange_rates': {
        'KRW': 1.0,
        'JPY': 9.5,
        'USD': 1350.0
    }
}


def ensure_data_dir():
    """데이터 디렉토리 생성"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if not os.path.exists(TRIPS_DIR):
        os.makedirs(TRIPS_DIR)


def load_settings() -> Dict[str, Any]:
    """저장된 설정 로드"""
    ensure_data_dir()
    if not os.path.exists(SETTINGS_FILE):
        # 기본 설정 저장 후 반환
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            # 누락된 키가 있으면 기본값으로 채우기
            for key, value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
    except (json.JSONDecodeError, FileNotFoundError):
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]):
    """설정 저장"""
    ensure_data_dir()
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ===== 여행 관리 함수들 =====

def list_trips() -> List[Dict[str, Any]]:
    """저장된 모든 여행 목록 반환"""
    ensure_data_dir()
    trips = []
    
    if not os.path.exists(TRIPS_DIR):
        return trips
    
    for filename in os.listdir(TRIPS_DIR):
        if filename.endswith('.json'):
            trip_path = os.path.join(TRIPS_DIR, filename)
            try:
                with open(trip_path, 'r', encoding='utf-8') as f:
                    trip_data = json.load(f)
                    trips.append({
                        'id': trip_data.get('id', filename.replace('.json', '')),
                        'title': trip_data.get('settings', {}).get('trip_title', '제목 없음'),
                        'created_at': trip_data.get('created_at', ''),
                        'archived_at': trip_data.get('archived_at', ''),
                        'expense_count': len(trip_data.get('expenses', [])),
                        'total_krw': sum(exp.get('krw_amount', 0) for exp in trip_data.get('expenses', []))
                    })
            except (json.JSONDecodeError, FileNotFoundError):
                continue
    
    # 아카이브 날짜 기준 최신순 정렬
    trips.sort(key=lambda x: x.get('archived_at', ''), reverse=True)
    return trips


def archive_current_trip() -> Optional[str]:
    """현재 여행을 아카이브하고 trip_id 반환"""
    ensure_data_dir()
    
    settings = load_settings()
    expenses = load_expenses()
    
    # 데이터가 없으면 아카이브하지 않음
    if not expenses and settings.get('trip_title') == DEFAULT_SETTINGS['trip_title']:
        return None
    
    # 새로운 trip ID 생성
    trip_id = str(uuid.uuid4())[:8]
    archived_at = datetime.now().isoformat()
    
    # 여행 데이터 구성
    trip_data = {
        'id': trip_id,
        'created_at': settings.get('created_at', archived_at),
        'archived_at': archived_at,
        'settings': settings,
        'expenses': expenses
    }
    
    # 아카이브 파일 저장
    trip_filename = f"{trip_id}.json"
    trip_path = os.path.join(TRIPS_DIR, trip_filename)
    
    with open(trip_path, 'w', encoding='utf-8') as f:
        json.dump(trip_data, f, ensure_ascii=False, indent=2, default=str)
    
    return trip_id


def create_new_trip(new_title: str, participants: List[str] = None, 
                    categories: List[str] = None, credit_card_fee_rate: float = 2.5) -> Dict[str, Any]:
    """새로운 여행 생성 (현재 데이터 초기화)"""
    ensure_data_dir()
    
    # 새 설정 생성
    new_settings = {
        'trip_id': None,
        'trip_title': new_title,
        'participants': participants or ['참가자1', '참가자2'],
        'categories': categories or ['교통비', '식사비', '음료/간식', '숙박비', '기타'],
        'credit_card_fee_rate': credit_card_fee_rate,
        'exchange_rates': DEFAULT_SETTINGS['exchange_rates'].copy(),
        'created_at': datetime.now().isoformat()
    }
    
    # 설정 저장
    save_settings(new_settings)
    
    # 경비 데이터 초기화
    save_expenses([])
    
    return new_settings


def load_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    """아카이브된 여행 불러오기"""
    ensure_data_dir()
    
    trip_path = os.path.join(TRIPS_DIR, f"{trip_id}.json")
    
    if not os.path.exists(trip_path):
        return None
    
    try:
        with open(trip_path, 'r', encoding='utf-8') as f:
            trip_data = json.load(f)
        
        # 현재 데이터로 복원
        settings = trip_data.get('settings', DEFAULT_SETTINGS.copy())
        settings['trip_id'] = trip_id  # 불러온 여행의 ID 저장
        expenses = trip_data.get('expenses', [])
        
        save_settings(settings)
        save_expenses(expenses)
        
        return {
            'settings': settings,
            'expenses': expenses
        }
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def delete_trip(trip_id: str) -> bool:
    """아카이브된 여행 삭제"""
    ensure_data_dir()
    
    trip_path = os.path.join(TRIPS_DIR, f"{trip_id}.json")
    
    if os.path.exists(trip_path):
        os.remove(trip_path)
        return True
    return False


def load_expenses() -> List[Dict[str, Any]]:
    """저장된 경비 데이터 로드"""
    ensure_data_dir()
    if not os.path.exists(DATA_FILE):
        return []
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_expenses(expenses: List[Dict[str, Any]]):
    """경비 데이터 저장"""
    ensure_data_dir()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(expenses, f, ensure_ascii=False, indent=2, default=str)


class JSONDatabase:
    """간단한 JSON 기반 데이터베이스"""
    
    @property
    def expenses(self):
        return ExpenseCollection()


class ExpenseCollection:
    """경비 컬렉션"""
    
    def find(self, filter_dict: Optional[Dict] = None):
        """경비 목록 조회"""
        expenses = load_expenses()
        if filter_dict:
            # 간단한 필터링
            filtered = []
            for exp in expenses:
                match = True
                for key, value in filter_dict.items():
                    if exp.get(key) != value:
                        match = False
                        break
                if match:
                    filtered.append(exp)
            return SortableCursor(filtered)
        return SortableCursor(expenses)
    
    def insert_one(self, document: Dict) -> 'InsertResult':
        """경비 추가"""
        expenses = load_expenses()
        doc_id = str(uuid.uuid4())
        document['_id'] = doc_id
        document['created_at'] = datetime.utcnow().isoformat()
        expenses.append(document)
        save_expenses(expenses)
        return InsertResult(doc_id)
    
    def delete_one(self, filter_dict: Dict) -> 'DeleteResult':
        """경비 삭제"""
        expenses = load_expenses()
        original_len = len(expenses)
        
        expenses = [exp for exp in expenses if exp.get('_id') != filter_dict.get('_id')]
        
        save_expenses(expenses)
        return DeleteResult(original_len - len(expenses))


class SortableCursor:
    """정렬 가능한 커서"""
    
    def __init__(self, data: List[Dict]):
        self._data = data
    
    def sort(self, field: str, direction: int = -1):
        """정렬"""
        reverse = direction == -1
        self._data = sorted(self._data, key=lambda x: x.get(field, ''), reverse=reverse)
        return self
    
    def __iter__(self):
        return iter(self._data)
    
    def __list__(self):
        return self._data


class InsertResult:
    def __init__(self, inserted_id: str):
        self.inserted_id = inserted_id


class DeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


def get_database() -> JSONDatabase:
    """데이터베이스 인스턴스 반환"""
    return JSONDatabase()


def close_connection():
    """연결 종료 (JSON 기반이므로 아무것도 하지 않음)"""
    pass
