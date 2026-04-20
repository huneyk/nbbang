"""이메일 인증코드 발급/검증 및 사용자 인증(비밀번호 + 이메일 코드)."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from email_validator import validate_email, EmailNotValidError
from flask_jwt_extended import create_access_token
from pymongo import ASCENDING
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from services import user_repository, trip_repository
from services.email_service import send_verification_code, EmailNotConfiguredError

logger = logging.getLogger(__name__)

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
VALID_PURPOSES = ('signup', 'login', 'reset')


class AuthError(Exception):
    """인증 관련 도메인 오류."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _verifications():
    from services.database import _get_db
    return _get_db().email_verifications


def ensure_indexes() -> None:
    coll = _verifications()
    coll.create_index([('email', ASCENDING), ('purpose', ASCENDING)])
    coll.create_index('expires_at', expireAfterSeconds=0)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _normalize_email(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise AuthError('이메일 주소를 입력하세요.', 400)
    try:
        validated = validate_email(raw.strip(), check_deliverability=False)
    except EmailNotValidError as e:
        raise AuthError(f'유효하지 않은 이메일 주소입니다: {e}', 400) from e
    return validated.normalized.lower()


def _normalize_purpose(raw: str) -> str:
    if raw not in VALID_PURPOSES:
        raise AuthError("purpose는 'signup', 'login', 'reset' 중 하나여야 합니다.", 400)
    return raw


def _validate_password(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise AuthError('비밀번호를 입력하세요.', 400)
    pw = raw.strip()
    if len(pw) < PASSWORD_MIN_LENGTH:
        raise AuthError(
            f'비밀번호는 최소 {PASSWORD_MIN_LENGTH}자 이상이어야 합니다.', 400,
        )
    if len(pw) > PASSWORD_MAX_LENGTH:
        raise AuthError(
            f'비밀번호는 최대 {PASSWORD_MAX_LENGTH}자까지 허용됩니다.', 400,
        )
    if ' ' in pw:
        raise AuthError('비밀번호에 공백을 포함할 수 없습니다.', 400)
    return pw


def _issue_token(user: Dict[str, Any]) -> str:
    return create_access_token(
        identity=user['id'],
        additional_claims={
            'email': user['email'],
            'is_admin': bool(user.get('is_admin')),
        },
    )


def request_verification_code(email: str, purpose: str) -> Dict[str, Any]:
    """인증코드 발급 후 메일 발송. (코드 자체는 응답에 포함하지 않음.)"""
    email = _normalize_email(email)
    purpose = _normalize_purpose(purpose)

    existing_user = user_repository.find_by_email(email)
    if purpose == 'signup' and existing_user:
        raise AuthError('이미 가입된 이메일입니다. 로그인을 이용하세요.', 409)
    if purpose in ('login', 'reset') and not existing_user:
        raise AuthError('가입되지 않은 이메일입니다. 회원가입을 진행하세요.', 404)

    coll = _verifications()
    cooldown_threshold = datetime.utcnow() - timedelta(
        seconds=Config.VERIFICATION_CODE_RESEND_COOLDOWN
    )
    recent = coll.find_one({
        'email': email,
        'purpose': purpose,
        'created_at_dt': {'$gte': cooldown_threshold},
    })
    if recent:
        raise AuthError(
            f'잠시 후 다시 시도해주세요. ({Config.VERIFICATION_CODE_RESEND_COOLDOWN}초 쿨다운)',
            429,
        )

    code = f'{secrets.randbelow(1_000_000):06d}'
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=Config.VERIFICATION_CODE_TTL_SECONDS)

    coll.delete_many({'email': email, 'purpose': purpose})
    coll.insert_one({
        'email': email,
        'purpose': purpose,
        'code_hash': _hash_code(code),
        'attempts': 0,
        'created_at': now.isoformat(),
        'created_at_dt': now,
        'expires_at': expires_at,
    })

    try:
        send_verification_code(email, code, purpose)
    except EmailNotConfiguredError as e:
        coll.delete_many({'email': email, 'purpose': purpose})
        raise AuthError(str(e), 500) from e
    except Exception as e:
        coll.delete_many({'email': email, 'purpose': purpose})
        logger.exception('메일 발송 실패')
        raise AuthError('메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.', 502) from e

    return {
        'email': email,
        'purpose': purpose,
        'expires_in': Config.VERIFICATION_CODE_TTL_SECONDS,
    }


def _consume_verification_code(email: str, purpose: str, code: str) -> None:
    """인증코드 검증 후 레코드 삭제. 실패 시 AuthError.

    Side effect: 성공/만료 시 해당 (email, purpose) 레코드를 삭제한다.
    """
    if not code or not isinstance(code, str) or not code.strip().isdigit():
        raise AuthError('인증번호를 6자리 숫자로 입력하세요.', 400)
    code = code.strip()

    coll = _verifications()
    record = coll.find_one({'email': email, 'purpose': purpose})
    if not record:
        raise AuthError('인증번호를 먼저 요청해주세요.', 404)

    if record.get('expires_at') and record['expires_at'] < datetime.utcnow():
        coll.delete_one({'_id': record['_id']})
        raise AuthError('인증번호가 만료되었습니다. 다시 요청해주세요.', 410)

    attempts = int(record.get('attempts', 0))
    if attempts >= Config.VERIFICATION_CODE_MAX_ATTEMPTS:
        coll.delete_one({'_id': record['_id']})
        raise AuthError('인증 시도 횟수를 초과했습니다. 다시 요청해주세요.', 429)

    if record.get('code_hash') != _hash_code(code):
        coll.update_one({'_id': record['_id']}, {'$inc': {'attempts': 1}})
        remaining = Config.VERIFICATION_CODE_MAX_ATTEMPTS - attempts - 1
        raise AuthError(
            f'인증번호가 일치하지 않습니다. (남은 시도 {max(remaining, 0)}회)', 400,
        )

    coll.delete_many({'email': email, 'purpose': purpose})


def verify_code_and_login(email: str, code: str, purpose: str,
                          name: str = '',
                          password: str = '') -> Tuple[Dict[str, Any], str]:
    """코드 검증 후 사용자 upsert·JWT 발급. (user, access_token) 반환.

    - purpose='signup': 비밀번호 필수. 신규 가입 + 비밀번호 저장.
    - purpose='login' : 코드 기반 폴백 로그인. 비밀번호는 무시.
    - purpose='reset' : 비밀번호 필수. 기존 사용자의 비밀번호를 재설정 후 로그인.
    """
    email = _normalize_email(email)
    purpose = _normalize_purpose(purpose)

    password_hash = ''
    if purpose in ('signup', 'reset'):
        validated_pw = _validate_password(password)
        password_hash = generate_password_hash(validated_pw)

    _consume_verification_code(email, purpose, code)

    user = user_repository.find_by_email(email)
    if user is None:
        if purpose != 'signup':
            raise AuthError('가입되지 않은 이메일입니다.', 404)
        is_admin = (
            bool(Config.ADMIN_EMAIL)
            and email == Config.ADMIN_EMAIL.strip().lower()
        )
        user = user_repository.create_user(
            email=email, name=name, is_admin=is_admin,
            password_hash=password_hash,
        )
        if is_admin:
            _migrate_legacy_data_to_admin(user['id'])
    else:
        if purpose == 'signup':
            # 이론상 도달 불가(request_code에서 차단) 방어적 처리
            raise AuthError('이미 가입된 이메일입니다. 로그인을 이용하세요.', 409)
        if purpose == 'reset':
            user_repository.set_password_hash(user['id'], password_hash)
            user = user_repository.find_by_id(user['id']) or user
        user_repository.touch_login(user['id'])

    # 신규 사용자/로그인 시점에는 비어있는 '새 여행'을 만들지 않는다.
    # 프론트엔드가 트립 미존재를 감지하여 새 여행 생성 모달을 자동으로 열어 준다.

    return user, _issue_token(user)


def login_with_password(email: str, password: str) -> Tuple[Dict[str, Any], str]:
    """이메일 + 비밀번호 기반 로그인. (user, access_token) 반환."""
    email = _normalize_email(email)
    if not password or not isinstance(password, str):
        raise AuthError('비밀번호를 입력하세요.', 400)

    user = user_repository.find_by_email(email)
    if user is None:
        raise AuthError('이메일 또는 비밀번호가 올바르지 않습니다.', 401)

    stored_hash = user_repository.find_password_hash_by_email(email)
    if not stored_hash:
        raise AuthError(
            '비밀번호가 설정되지 않은 계정입니다. 인증번호로 로그인 후 비밀번호를 설정해주세요.',
            409,
        )

    if not check_password_hash(stored_hash, password):
        raise AuthError('이메일 또는 비밀번호가 올바르지 않습니다.', 401)

    user_repository.touch_login(user['id'])

    return user, _issue_token(user)


def set_password_for_user(user_id: str, new_password: str,
                          current_password: Optional[str] = None) -> Dict[str, Any]:
    """로그인된 사용자의 비밀번호 설정/변경.

    - 기존 비밀번호가 있으면 current_password 확인 필수.
    - 최초 설정(아직 비밀번호 미설정)에는 current_password 불필요.
    """
    user = user_repository.find_by_id(user_id)
    if not user:
        raise AuthError('사용자를 찾을 수 없습니다.', 404)

    validated_pw = _validate_password(new_password)

    existing_hash = user_repository.find_password_hash(user_id)
    if existing_hash:
        if not current_password:
            raise AuthError('현재 비밀번호를 입력해주세요.', 400)
        if not check_password_hash(existing_hash, current_password):
            raise AuthError('현재 비밀번호가 올바르지 않습니다.', 401)
        if check_password_hash(existing_hash, validated_pw):
            raise AuthError('새 비밀번호가 기존 비밀번호와 동일합니다.', 400)

    new_hash = generate_password_hash(validated_pw)
    if not user_repository.set_password_hash(user_id, new_hash):
        raise AuthError('비밀번호 변경에 실패했습니다.', 500)

    return user_repository.find_by_id(user_id) or user


# ===== 마이그레이션 =====

def _migrate_legacy_data_to_admin(admin_user_id: str) -> None:
    """기존 단일 테넌트 데이터(전역 settings/expenses/trips)를 admin 사용자로 이관.

    - 기존 ``app_settings`` 컬렉션의 google/koreaexim 키가 평문으로 남아있다면
      app_settings_service를 통해 다시 저장(암호화)한다.
    - 기존 ``expenses`` 컬렉션의 모든 문서를 새 활성 트립으로 묶는다.
    - 기존 ``trips`` 컬렉션의 (사용자 미지정) 아카이브 트립에 user_id를 부여한다.
    """
    from services.database import _get_db
    from services import app_settings_service

    if app_settings_service.is_migrated():
        logger.info('이미 마이그레이션 완료된 상태이므로 건너뜀')
        return

    db = _get_db()

    # 1) 기존 settings 컬렉션의 키를 app_settings로 이전
    legacy_settings_doc = db.settings.find_one({'_type': 'app_settings'}) or {}
    legacy_google = legacy_settings_doc.get('google_api_key') or ''
    legacy_koreaexim = legacy_settings_doc.get('koreaexim_api_key') or ''
    if legacy_google or legacy_koreaexim:
        from services.encryption import decrypt_value
        updates = {}
        if legacy_google:
            updates['google_api_key'] = decrypt_value(legacy_google)
        if legacy_koreaexim:
            updates['koreaexim_api_key'] = decrypt_value(legacy_koreaexim)
        app_settings_service.update_app_settings(updates)
        logger.info('기존 settings의 API 키를 app_settings로 이전')

    # 환경 변수 키도 시드
    app_settings_service.seed_keys_from_env_if_missing()

    # 2) 기존 expenses 컬렉션의 문서들을 admin의 새 활성 트립으로 묶기
    legacy_expenses = list(db.expenses.find())
    if legacy_expenses:
        title = legacy_settings_doc.get('trip_title') or '기존 여행'
        participants = legacy_settings_doc.get('participants') or []
        categories = legacy_settings_doc.get(
            'categories', list(trip_repository.DEFAULT_CATEGORIES),
        )
        credit_card_fee_rate = legacy_settings_doc.get('credit_card_fee_rate', 2.5)
        currencies = legacy_settings_doc.get(
            'currencies', list(trip_repository.DEFAULT_CURRENCIES),
        )
        exchange_rates = legacy_settings_doc.get('exchange_rates') or {
            c['code']: c['rate'] for c in currencies
        }

        new_trip = trip_repository.create_trip(
            user_id=admin_user_id,
            trip_title=title,
            participants=participants,
            categories=categories,
            credit_card_fee_rate=credit_card_fee_rate,
            make_active=True,
        )
        # 기존 통화/환율을 그대로 이식
        trip_repository.update_trip_settings(
            admin_user_id, new_trip['trip_id'],
            {
                'currencies': currencies,
                'exchange_rates': exchange_rates,
                'exchange_rate_info': legacy_settings_doc.get('exchange_rate_info', {}),
            },
        )

        # 경비 임베드
        sanitized = []
        for exp in legacy_expenses:
            doc = dict(exp)
            doc.pop('_id', None)
            doc.setdefault('id', secrets.token_hex(8))
            sanitized.append(doc)

        from bson import ObjectId
        db.trips.update_one(
            {'_id': ObjectId(new_trip['_id'])},
            {'$set': {'expenses': sanitized,
                      'updated_at': datetime.utcnow().isoformat()}},
        )
        logger.info(f'기존 expenses {len(sanitized)}건을 새 트립으로 이관')

        db.expenses.delete_many({})

    # 3) 기존 trips(아카이브) 문서에 user_id 부여
    archived_count = db.trips.update_many(
        {'user_id': {'$exists': False}},
        {'$set': {'user_id': admin_user_id, 'is_active': False}},
    ).modified_count
    if archived_count:
        logger.info(f'아카이브된 trips {archived_count}건에 admin user_id 부여')

    # 4) 마이그레이션 완료 플래그
    app_settings_service.mark_migrated()
    logger.info('마이그레이션 완료')


def ensure_admin_account_from_env() -> None:
    """환경변수(ADMIN_EMAIL/ADMIN_PASSWORD)로 admin 계정을 생성/동기화.

    - 둘 중 하나라도 비어 있으면 아무 것도 하지 않음.
    - 계정이 없으면 생성(is_admin=True, 비밀번호 해시 저장) 후 레거시 데이터 이관.
    - 계정이 있으면 is_admin=True 보장 + 비밀번호가 env와 다를 때만 해시 갱신.
    """
    raw_email = (Config.ADMIN_EMAIL or '').strip().lower()
    raw_password = Config.ADMIN_PASSWORD or ''
    if not raw_email or not raw_password:
        logger.info('ADMIN_EMAIL/ADMIN_PASSWORD 미설정 → admin seed 건너뜀')
        return

    try:
        email = _normalize_email(raw_email)
        password = _validate_password(raw_password)
    except AuthError as e:
        logger.warning(f'admin seed 입력 검증 실패: {e.message}')
        return

    existing = user_repository.find_by_email(email)
    if existing is None:
        password_hash = generate_password_hash(password)
        user = user_repository.create_user(
            email=email, name='Admin', is_admin=True,
            password_hash=password_hash,
        )
        logger.info(f'admin 계정 신규 생성: {email}')
        try:
            _migrate_legacy_data_to_admin(user['id'])
        except Exception:
            logger.exception('admin 레거시 데이터 이관 실패')
        try:
            trip_repository.get_or_create_active_trip(user['id'], default_title='새 여행')
        except Exception:
            logger.exception('admin 기본 트립 생성 실패')
        return

    if not existing.get('is_admin'):
        user_repository.update_user(existing['id'], {'is_admin': True})
        logger.info(f'기존 계정에 admin 권한 부여: {email}')

    stored_hash = user_repository.find_password_hash_by_email(email)
    if not stored_hash or not check_password_hash(stored_hash, password):
        user_repository.set_password_hash(existing['id'], generate_password_hash(password))
        logger.info(f'admin 비밀번호를 환경변수 값으로 동기화: {email}')


def get_current_user_payload(claims: Dict[str, Any], identity: str) -> Optional[Dict[str, Any]]:
    """JWT 클레임 + identity로부터 사용자 정보를 재조회."""
    user = user_repository.find_by_id(identity)
    if not user:
        return None
    return {
        'id': user['id'],
        'email': user['email'],
        'name': user.get('name', ''),
        'is_admin': bool(user.get('is_admin')),
    }
