"""이메일 인증 + 비밀번호 기반 회원가입/로그인 라우트."""
import logging
from flask import Blueprint, request, jsonify

from decorators import login_required, get_current_user_id
from services import auth_service, user_repository

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _public_user(user: dict) -> dict:
    return {
        'id': user['id'],
        'email': user['email'],
        'name': user.get('name', ''),
        'is_admin': bool(user.get('is_admin')),
        'has_password': bool(user.get('has_password')),
        'credit_card_fee_rate': float(
            user.get('credit_card_fee_rate',
                     user_repository.DEFAULT_CREDIT_CARD_FEE_RATE),
        ),
    }


@auth_bp.route('/request-code', methods=['POST'])
def request_code():
    """{ email, purpose } -> 인증코드 메일 발송. purpose: signup | login | reset."""
    data = request.json or {}
    try:
        result = auth_service.request_verification_code(
            email=data.get('email', ''),
            purpose=data.get('purpose', ''),
        )
    except auth_service.AuthError as e:
        return jsonify({'success': False, 'error': e.message}), e.status_code
    return jsonify({'success': True, 'data': result})


@auth_bp.route('/verify-code', methods=['POST'])
def verify_code():
    """{ email, code, purpose, name?, password? } -> JWT 발급.

    - signup: password 필수
    - login : password 무시 (폴백 로그인)
    - reset : password 필수 (기존 사용자 비밀번호 재설정 후 로그인)
    """
    data = request.json or {}
    try:
        user, access_token = auth_service.verify_code_and_login(
            email=data.get('email', ''),
            code=data.get('code', ''),
            purpose=data.get('purpose', ''),
            name=data.get('name', ''),
            password=data.get('password', ''),
        )
    except auth_service.AuthError as e:
        return jsonify({'success': False, 'error': e.message}), e.status_code

    return jsonify({
        'success': True,
        'data': {
            'access_token': access_token,
            'user': _public_user(user),
        },
    })


@auth_bp.route('/login', methods=['POST'])
def login_password():
    """{ email, password } -> JWT 발급 (비밀번호 로그인)."""
    data = request.json or {}
    try:
        user, access_token = auth_service.login_with_password(
            email=data.get('email', ''),
            password=data.get('password', ''),
        )
    except auth_service.AuthError as e:
        return jsonify({'success': False, 'error': e.message}), e.status_code

    return jsonify({
        'success': True,
        'data': {
            'access_token': access_token,
            'user': _public_user(user),
        },
    })


@auth_bp.route('/set-password', methods=['POST'])
@login_required
def set_password():
    """{ current_password?, new_password } -> 비밀번호 설정/변경.

    최초 설정(아직 비밀번호 없음)은 current_password 없이 가능.
    """
    data = request.json or {}
    try:
        user = auth_service.set_password_for_user(
            user_id=get_current_user_id(),
            new_password=data.get('new_password', ''),
            current_password=data.get('current_password') or None,
        )
    except auth_service.AuthError as e:
        return jsonify({'success': False, 'error': e.message}), e.status_code

    return jsonify({'success': True, 'data': {'user': _public_user(user)}})


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    user = user_repository.find_by_id(get_current_user_id())
    if not user:
        return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 404
    return jsonify({'success': True, 'data': _public_user(user)})


@auth_bp.route('/me', methods=['PATCH'])
@login_required
def update_me():
    """현재 로그인 사용자의 프로필 필드(수수료율 등) 부분 갱신."""
    data = request.json or {}
    updates: dict = {}
    if 'credit_card_fee_rate' in data:
        updates['credit_card_fee_rate'] = data['credit_card_fee_rate']
    if 'name' in data:
        updates['name'] = data['name']

    if not updates:
        return jsonify({'success': False, 'error': '변경할 필드가 없습니다.'}), 400

    user = user_repository.update_user(get_current_user_id(), updates)
    if not user:
        return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 404
    return jsonify({'success': True, 'data': _public_user(user)})


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """클라이언트가 토큰을 폐기. 서버는 무상태."""
    return jsonify({'success': True})
