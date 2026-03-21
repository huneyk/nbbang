import os
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
    
    # 참가자 명단
    PARTICIPANTS = ['공훈의', '최철기', '이태수', '강경수']
    
    # 지출 항목
    EXPENSE_CATEGORIES = ['교통비', '식사비', '음료/간식', '숙박비', '기타']
