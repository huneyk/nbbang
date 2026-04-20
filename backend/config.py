import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'Tour-expense')
    KOREAEXIM_API_KEY = os.getenv('KOREAEXIM_API_KEY', '')
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # JWT 설정
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    # 헤더(Bearer)와 쿼리 스트링(?jwt=) 양쪽 지원: <img src=>에 Bearer를 붙일 수 없으므로
    # 영수증 이미지 등은 쿼리스트링으로 토큰 전달
    JWT_TOKEN_LOCATION = ['headers', 'query_string']
    JWT_QUERY_STRING_NAME = 'jwt'

    # 관리자 이메일 (가입 시 자동 admin 권한 부여)
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '').strip().lower()
    # 관리자 비밀번호 (앱 시작 시 admin 계정을 자동 생성/동기화; 비어 있으면 시드 생략)
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')

    # Gmail SMTP (인증코드 메일 발송)
    GMAIL_USER = os.getenv('GMAIL_USER', '')
    GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
    MAIL_FROM_NAME = os.getenv('MAIL_FROM_NAME', 'Npang')

    # 인증코드 정책
    VERIFICATION_CODE_TTL_SECONDS = 600  # 10분
    VERIFICATION_CODE_RESEND_COOLDOWN = 60  # 60초
    VERIFICATION_CODE_MAX_ATTEMPTS = 5

    # 환율 설정 (KRW 기준)
    EXCHANGE_RATES = {
        'KRW': 1.0,
        'USD': 1350.0,
        'JPY': 9.5,
        'CNY': 185.0,
        'EUR': 1480.0,
        'HKD': 173.0,
    }

    SCHEDULER_API_ENABLED = False

    # 신용카드 수수료율
    CREDIT_CARD_FEE_RATE = 0.025  # 2.5%

    # 참가자 명단 (신규 트립 기본값)
    PARTICIPANTS = ['공훈의', '최철기', '이태수', '강경수']

    # 지출 항목
    EXPENSE_CATEGORIES = ['교통비', '식사비', '음료/간식', '숙박비', '기타']
