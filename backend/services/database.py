import json
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from config import Config


# JSON 파일 기반 간단한 데이터베이스
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'expenses.json')


def ensure_data_dir():
    """데이터 디렉토리 생성"""
    data_dir = os.path.dirname(DATA_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


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
