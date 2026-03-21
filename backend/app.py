import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from config import Config
from routes.expense_routes import expense_bp
from services.database import close_connection


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
    
    CORS(app, resources={r"/api/*": {
        "origins": "*",
        "expose_headers": ["Content-Disposition"]
    }}, supports_credentials=True)
    
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    app.register_blueprint(expense_bp)
    
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
