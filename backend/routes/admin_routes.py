"""관리자 전용 엔드포인트.

- 전역 API 키(google_api_key, koreaexim_api_key) 관리
- 사용자 현황 통계
- 회원 관리 (권한 변경, 삭제, 비밀번호 초기화)
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

from decorators import admin_required, get_current_user_id
from services import app_settings_service, trip_repository, user_repository

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


# ===== API 키 관리 =====

@admin_bp.route('/app-settings', methods=['GET'])
@admin_required
def get_app_settings():
    """API 키 설정 여부만 마스킹된 형태로 반환."""
    return jsonify({'success': True, 'data': app_settings_service.get_masked_settings()})


@admin_bp.route('/app-settings', methods=['PUT'])
@admin_required
def update_app_settings():
    """{ google_api_key?, koreaexim_api_key? } 저장. 빈 문자열 전송 시 삭제."""
    data = request.json or {}
    updates = {k: v for k, v in data.items()
               if k in ('google_api_key', 'koreaexim_api_key')}
    if not updates:
        return jsonify({'success': False, 'error': '갱신할 키가 없습니다.'}), 400
    masked = app_settings_service.update_app_settings(updates)
    return jsonify({'success': True, 'data': masked})


# ===== 사용자 현황 (통계) =====

@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    """전반적인 사용 현황 반환."""
    now = datetime.utcnow()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    totals = trip_repository.aggregate_global_stats()
    stats = {
        'users': {
            'total': user_repository.count_users(),
            'admins': user_repository.count_admins(),
            'active_7d': user_repository.count_recent_logins(week_ago),
            'active_30d': user_repository.count_recent_logins(month_ago),
            'signups_7d': user_repository.count_recent_signups(week_ago),
            'signups_30d': user_repository.count_recent_signups(month_ago),
        },
        'trips': {
            'total': totals['trip_count'],
        },
        'expenses': {
            'total_count': totals['expense_count'],
            'total_krw': totals['total_krw'],
        },
        'generated_at': now.isoformat(),
    }
    return jsonify({'success': True, 'data': stats})


# ===== 회원 관리 =====

def _user_view(user: dict, with_stats: bool = False) -> dict:
    view = {
        'id': user['id'],
        'email': user['email'],
        'name': user.get('name', ''),
        'is_admin': bool(user.get('is_admin')),
        'has_password': bool(user.get('has_password')),
        'created_at': user.get('created_at', ''),
        'last_login_at': user.get('last_login_at', ''),
    }
    if with_stats:
        view['stats'] = trip_repository.aggregate_stats_by_user(user['id'])
    return view


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    with_stats = request.args.get('with_stats', '').lower() in ('1', 'true', 'yes')
    users = [_user_view(u, with_stats=with_stats) for u in user_repository.list_users()]
    return jsonify({'success': True, 'data': users})


@admin_bp.route('/users/<user_id>', methods=['PATCH'])
@admin_required
def update_user(user_id: str):
    """회원 정보 일부 갱신: { is_admin?, name? }."""
    data = request.json or {}

    if 'is_admin' in data and not data['is_admin']:
        current_admin_id = get_current_user_id()
        if user_id == current_admin_id:
            return jsonify({
                'success': False,
                'error': '자기 자신의 관리자 권한은 해제할 수 없습니다.',
            }), 400
        if user_repository.count_admins() <= 1:
            return jsonify({
                'success': False,
                'error': '최소 1명의 관리자는 유지되어야 합니다.',
            }), 400

    updated = user_repository.update_user(user_id, data)
    if not updated:
        return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 404
    return jsonify({'success': True, 'data': _user_view(updated)})


@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id: str):
    """사용자와 모든 트립/경비를 삭제."""
    current_admin_id = get_current_user_id()
    if user_id == current_admin_id:
        return jsonify({
            'success': False,
            'error': '자기 자신은 삭제할 수 없습니다.',
        }), 400

    target = user_repository.find_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 404

    if target.get('is_admin') and user_repository.count_admins() <= 1:
        return jsonify({
            'success': False,
            'error': '최소 1명의 관리자는 유지되어야 합니다.',
        }), 400

    trips_deleted = trip_repository.delete_trips_by_user(user_id)
    user_repository.delete_user(user_id)
    return jsonify({
        'success': True,
        'data': {'user_id': user_id, 'trips_deleted': trips_deleted},
    })


@admin_bp.route('/users/<user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id: str):
    """사용자의 비밀번호를 제거해 재설정을 강제한다.

    사용자는 다음 로그인 시 ``reset`` 플로우(이메일 인증코드 + 새 비밀번호)로
    비밀번호를 다시 설정해야 한다.
    """
    target = user_repository.find_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'error': '사용자를 찾을 수 없습니다.'}), 404

    user_repository.clear_password(user_id)
    return jsonify({
        'success': True,
        'data': {
            'user_id': user_id,
            'message': '비밀번호가 초기화되었습니다. 사용자는 이메일 인증으로 재설정해야 합니다.',
        },
    })
