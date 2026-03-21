import os
import logging
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_apscheduler import APScheduler
from werkzeug.exceptions import RequestEntityTooLarge
from config import Config
from routes.expense_routes import expense_bp
from services.database import close_connection, load_settings, save_settings

logger = logging.getLogger(__name__)
scheduler = APScheduler()


def scheduled_exchange_rate_update():
    """매일 오전 4시에 실행되는 환율 자동 갱신 작업"""
    from services.exchange_rate_service import fetch_exchange_rates, apply_fetched_rates

    with scheduler.app.app_context():
        try:
            settings = load_settings()
            result = fetch_exchange_rates(settings)

            if result.get('rates'):
                updated = apply_fetched_rates(settings, result)
                save_settings(updated)
                logger.info(
                    f"환율 자동 갱신 완료: {result['source']} "
                    f"({len(result['rates'])}개 통화)"
                )
            else:
                logger.warning('환율 자동 갱신 실패: 조회된 환율 없음')
        except Exception as e:
            logger.error(f'환율 자동 갱신 오류: {e}')


def create_app():
    """Flask 애플리케이션 팩토리"""
    static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    has_static = os.path.isdir(static_folder)

    if has_static:
        app = Flask(__name__, static_folder=static_folder, static_url_path='')
    else:
        app = Flask(__name__)

    app.config.from_object(Config)
    
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

    # APScheduler: 매일 오전 4시 (KST) 환율 자동 갱신
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
        "origins": "*",
        "expose_headers": ["Content-Disposition"]
    }}, supports_credentials=True)
    
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    app.register_blueprint(expense_bp)

    # 스케줄러 시작 (debug reloader 중복 방지)
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
        from services.ocr_service import get_google_api_key
        api_key_set = bool(get_google_api_key())
        return {
            'status': 'ok', 
            'message': '여행 경비 정산 API 서버가 실행 중입니다.',
            'google_api_key_configured': api_key_set
        }
    
    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error):
        return jsonify({
            'success': False,
            'error': '파일이 너무 큽니다. 최대 50MB까지 업로드 가능합니다.'
        }), 413
    
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        pass

    import atexit
    atexit.register(close_connection)
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)
