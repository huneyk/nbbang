import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from config import Config
from routes.expense_routes import expense_bp
from services.database import close_connection


def create_app():
    """Flask 애플리케이션 팩토리"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # 파일 업로드 크기 제한 명시적 설정 (50MB)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
    
    # CORS 설정 - 모든 원본 허용, Content-Disposition 헤더 노출
    CORS(app, resources={r"/api/*": {
        "origins": "*",
        "expose_headers": ["Content-Disposition"]
    }}, supports_credentials=True)
    
    # 업로드 폴더 생성
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    # Blueprint 등록
    app.register_blueprint(expense_bp)
    
    # 업로드된 이미지 서빙
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(Config.UPLOAD_FOLDER, filename)
    
    # Health check
    @app.route('/api/health')
    def health_check():
        from services.ocr_service import get_google_api_key
        api_key_set = bool(get_google_api_key())
        return {
            'status': 'ok', 
            'message': '여행 경비 정산 API 서버가 실행 중입니다.',
            'google_api_key_configured': api_key_set
        }
    
    # 파일 크기 초과 에러 핸들러
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
