import os
import re
import logging

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_apscheduler import APScheduler
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import RequestEntityTooLarge

from config import Config
from routes.expense_routes import expense_bp
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from services.database import close_connection

logger = logging.getLogger(__name__)
scheduler = APScheduler()
jwt = JWTManager()


def scheduled_exchange_rate_update():
    """매일 오전 4시: 모든 사용자 active 트립의 환율을 갱신.

    개별 사용자별 환율을 모두 갱신하기에는 무겁고 키 조회는 전역 admin 키를 쓰므로,
    이 잡은 단순히 1회 환율 fetch만 수행하여 캐시 형태로 활용한다.
    각 사용자는 다음 요청 시점에 자신의 트립 settings를 직접 갱신한다.
    """
    from services.exchange_rate_service import fetch_exchange_rates
    from services.trip_repository import _default_settings

    with scheduler.app.app_context():
        try:
            seed_settings = _default_settings()
            result = fetch_exchange_rates(seed_settings)
            if result.get('rates'):
                logger.info(
                    f"환율 자동 조회 완료: {result['source']} "
                    f"({len(result['rates'])}개 통화). 사용자별 적용은 다음 fetch 호출에 위임."
                )
            else:
                logger.warning('환율 자동 조회 실패: 조회된 환율 없음')
        except Exception as e:
            logger.error(f'환율 자동 갱신 오류: {e}')


def _initialize_database():
    """필요한 인덱스를 생성하고 환경변수 키를 시드."""
    from services import user_repository, trip_repository, auth_service, app_settings_service
    try:
        user_repository.ensure_indexes()
        trip_repository.ensure_indexes()
        auth_service.ensure_indexes()
        app_settings_service.seed_keys_from_env_if_missing()
        auth_service.ensure_admin_account_from_env()
        logger.info('DB 인덱스 초기화 및 환경변수 키/admin 시드 완료')
    except Exception as e:
        logger.warning(f'DB 초기화 경고: {e}')


def create_app():
    """Flask 애플리케이션 팩토리."""
    static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    has_static = os.path.isdir(static_folder)

    if has_static:
        app = Flask(__name__, static_folder=static_folder, static_url_path='')
    else:
        app = Flask(__name__)

    app.config.from_object(Config)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

    app.config['SCHEDULER_TIMEZONE'] = 'Asia/Seoul'
    app.config['SCHEDULER_JOBS'] = [
        {
            'id': 'exchange_rate_update',
            'func': 'app:scheduled_exchange_rate_update',
            'trigger': 'cron',
            'hour': 4,
            'minute': 0,
            'misfire_grace_time': 3600,
        }
    ]

    CORS(app, resources={r"/api/*": {
        "origins": [re.compile(r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$")],
        "expose_headers": ["Content-Disposition"],
        "allow_headers": ["Content-Type", "Authorization"],
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    }}, supports_credentials=True)

    jwt.init_app(app)

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(expense_bp)

    with app.app_context():
        _initialize_database()

    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if not app.debug or is_reloader:
        scheduler.init_app(app)
        scheduler.start()
        logger.info('환율 자동 갱신 스케줄러 시작 (매일 04:00 KST)')

    if has_static:
        @app.route('/')
        def serve_react():
            return send_from_directory(static_folder, 'index.html')

        @app.route('/<path:path>')
        def serve_static(path):
            if path.startswith('api/'):
                return jsonify({'error': 'Not found'}), 404
            file_path = os.path.join(static_folder, path)
            if os.path.exists(file_path):
                return send_from_directory(static_folder, path)
            return send_from_directory(static_folder, 'index.html')

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(Config.UPLOAD_FOLDER, filename)

    @app.route('/api/health')
    def health_check():
        from services.app_settings_service import get_masked_settings
        masked = get_masked_settings()
        return {
            'status': 'ok',
            'message': '여행 경비 정산 API 서버가 실행 중입니다.',
            'google_api_key_configured': masked.get('google_api_key_set'),
            'koreaexim_api_key_configured': masked.get('koreaexim_api_key_set'),
            'gmail_configured': bool(Config.GMAIL_USER and Config.GMAIL_APP_PASSWORD),
        }

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error):
        return jsonify({
            'success': False,
            'error': '파일이 너무 큽니다. 최대 50MB까지 업로드 가능합니다.'
        }), 413

    @jwt.unauthorized_loader
    def _missing_token(reason):
        return jsonify({'success': False, 'error': '로그인이 필요합니다.', 'detail': reason}), 401

    @jwt.invalid_token_loader
    def _invalid_token(reason):
        return jsonify({'success': False, 'error': '유효하지 않은 토큰입니다.', 'detail': reason}), 401

    @jwt.expired_token_loader
    def _expired_token(jwt_header, jwt_payload):
        return jsonify({'success': False, 'error': '로그인 세션이 만료되었습니다.'}), 401

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        pass

    import atexit
    atexit.register(close_connection)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)
