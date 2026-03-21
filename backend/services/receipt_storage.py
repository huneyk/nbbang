"""
영수증 이미지 GridFS 저장 서비스
- MongoDB GridFS를 사용하여 영수증 이미지를 저장/조회/삭제
- Collection: receipts (receipts.files + receipts.chunks)
"""

import logging

import certifi
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
from config import Config

logger = logging.getLogger(__name__)

_client = None
_gridfs = None


def _get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            Config.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where()
        )
    return _client


def _get_gridfs() -> GridFS:
    global _gridfs
    if _gridfs is None:
        client = _get_mongo_client()
        db = client[Config.DATABASE_NAME]
        _gridfs = GridFS(db, collection='receipts')
    return _gridfs


def save_receipt(file_path: str, filename: str, content_type: str = 'image/jpeg') -> str:
    """영수증 이미지를 GridFS에 저장합니다. file_id 문자열을 반환합니다."""
    fs = _get_gridfs()
    with open(file_path, 'rb') as f:
        file_id = fs.put(
            f.read(),
            filename=filename,
            content_type=content_type
        )
    logger.info(f"GridFS 저장 완료: {filename} (id: {file_id})")
    return str(file_id)


def get_receipt(file_id: str):
    """GridFS에서 영수증 이미지를 조회합니다. GridOut 객체를 반환합니다."""
    fs = _get_gridfs()
    try:
        return fs.get(ObjectId(file_id))
    except Exception as e:
        logger.error(f"GridFS 조회 실패 (id: {file_id}): {e}")
        return None


def delete_receipt(file_id: str) -> bool:
    """GridFS에서 영수증 이미지를 삭제합니다."""
    fs = _get_gridfs()
    try:
        fs.delete(ObjectId(file_id))
        logger.info(f"GridFS 삭제 완료 (id: {file_id})")
        return True
    except Exception as e:
        logger.error(f"GridFS 삭제 실패 (id: {file_id}): {e}")
        return False


def close_connection():
    """MongoDB 연결을 종료합니다."""
    global _client, _gridfs
    if _client:
        _client.close()
        _client = None
        _gridfs = None
