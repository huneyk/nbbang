"""
macOS 데스크톱 앱용 Flask 애플리케이션
빌드된 React 정적 파일을 함께 서빙합니다.
"""
import os
import sys
import webbrowser
import threading
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from config import Config
from routes.expense_routes import expense_bp
from services.database import close_connection


def get_resource_path(relative_path: str) -> str:
    """PyInstaller 번들에서 리소스 경로를 가져옵니다."""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 번들 내부
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def get_data_path() -> str:
    """사용자 데이터 저장 경로를 반환합니다."""
    if hasattr(sys, '_MEIPASS'):
        # 앱 번들 외부의 사용자 데이터 폴더 사용
        app_support = os.path.expanduser('~/Library/Application Support/TourExpense')
        os.makedirs(app_support, exist_ok=True)
        return app_support
    return os.path.dirname(os.path.abspath(__file__))


def create_desktop_app():
    """데스크톱용 Flask 애플리케이션 팩토리"""
    # 정적 파일 경로 설정
    static_folder = get_resource_path('static')
    
    app = Flask(__name__, static_folder=static_folder, static_url_path='')
    app.config.from_object(Config)
    
    # 업로드 폴더를 사용자 데이터 경로로 설정
    data_path = get_data_path()
    app.config['UPLOAD_FOLDER'] = os.path.join(data_path, 'uploads')
    app.config['DATA_FOLDER'] = os.path.join(data_path, 'data')
    
    # 파일 업로드 크기 제한 (50MB)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
    
    # CORS 설정
    CORS(app, resources={r"/api/*": {
        "origins": "*",
        "expose_headers": ["Content-Disposition"]
    }}, supports_credentials=True)
    
    # 필요한 폴더 생성
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)
    
    # Blueprint 등록
    app.register_blueprint(expense_bp)
    
    # React 앱 서빙 (정적 파일)
    @app.route('/')
    def serve_react():
        return send_from_directory(static_folder, 'index.html')
    
    @app.route('/<path:path>')
    def serve_static(path):
        if path.startswith('api/'):
            return jsonify({'error': 'Not found'}), 404
        if os.path.exists(os.path.join(static_folder, path)):
            return send_from_directory(static_folder, path)
        return send_from_directory(static_folder, 'index.html')
    
    # 업로드된 이미지 서빙
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
    # Health check
    @app.route('/api/health')
    def health_check():
        from services.ocr_service import get_openai_api_key
        api_key_set = bool(get_openai_api_key())
        return {
            'status': 'ok', 
            'message': '여행 경비 정산 API 서버가 실행 중입니다.',
            'openai_api_key_configured': api_key_set,
            'desktop_mode': True
        }
    
    # 파일 크기 초과 에러 핸들러
    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error):
        return jsonify({
            'success': False,
            'error': '파일이 너무 큽니다. 최대 50MB까지 업로드 가능합니다.'
        }), 413
    
    return app


def open_browser():
    """브라우저를 열어 앱에 접속합니다."""
    webbrowser.open('http://localhost:5001')


def main():
    """메인 진입점"""
    app = create_desktop_app()
    
    # 1초 후 브라우저 열기
    threading.Timer(1.0, open_browser).start()
    
    print("=" * 50)
    print("🌏 여행 경비 정산 앱이 시작되었습니다!")
    print("=" * 50)
    print("브라우저에서 http://localhost:5001 에 접속하세요.")
    print("종료하려면 Ctrl+C 를 누르세요.")
    print("=" * 50)
    
    # 서버 실행 (디버그 모드 OFF)
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
