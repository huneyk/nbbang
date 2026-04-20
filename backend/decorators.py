"""인증/인가 데코레이터."""
from functools import wraps
from flask import jsonify
from flask_jwt_extended import (
    verify_jwt_in_request, get_jwt, get_jwt_identity,
)


def login_required(fn):
    """JWT가 유효해야 접근 가능."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            return jsonify({'success': False, 'error': '로그인이 필요합니다.', 'detail': str(e)}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    """JWT 클레임의 is_admin이 True여야 접근 가능."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            return jsonify({'success': False, 'error': '로그인이 필요합니다.', 'detail': str(e)}), 401
        claims = get_jwt()
        if not claims.get('is_admin'):
            return jsonify({'success': False, 'error': '관리자 권한이 필요합니다.'}), 403
        return fn(*args, **kwargs)
    return wrapper


def get_current_user_id() -> str:
    return get_jwt_identity()


def get_current_user_claims() -> dict:
    return get_jwt()
