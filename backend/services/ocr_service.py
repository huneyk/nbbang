import base64
import re
import json
import logging
from datetime import datetime
from typing import Optional
import google.generativeai as genai
from PIL import Image
from config import Config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_google_api_key() -> str:
    """
    Google API 키를 가져옵니다.
    1. Config에서 먼저 확인 (환경변수 또는 런타임 설정)
    2. 없으면 settings 파일에서 확인
    """
    if Config.GOOGLE_API_KEY:
        return Config.GOOGLE_API_KEY
    
    from services.database import load_settings
    settings = load_settings()
    api_key = settings.get('google_api_key', '')
    
    if api_key:
        Config.GOOGLE_API_KEY = api_key
    
    return api_key


def analyze_receipt_with_gemini(image_path: str) -> dict:
    """
    Gemini 2.5 Flash를 사용하여 영수증을 분석합니다.
    일본어, 한국어, 영어 영수증을 지원합니다.
    """
    logger.info(f"영수증 분석 시작: {image_path}")
    
    api_key = get_google_api_key()
    
    if not api_key:
        logger.error("Google API 키가 설정되지 않았습니다.")
        return {
            'success': False,
            'error': 'Google API 키가 설정되지 않았습니다. 설정에서 Google API Key를 입력해주세요.',
            'data': None
        }
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        img = Image.open(image_path)
        
        prompt = """당신은 다국어 영수증 OCR 분석 전문가입니다.

## 전문 분야
- 일본어 (日本語) 영수증 분석
- 한국어 영수증 분석
- 영어 영수증 분석
- 중국어 (中文) 영수증 분석
- 유럽 각국어 영수증 분석

## 날짜 형식 인식
일본 영수증의 다양한 날짜 형식을 정확히 인식하세요:
- 西暦: 2024年1月18日, 2024/01/18, 24.01.18
- 令和: R6年1月18日, 令和6年1月18日 → 2024-01-18
- 平成: H31年4月30日, 平成31年4月30日 → 2019-04-30
유럽 날짜: DD/MM/YYYY 또는 DD.MM.YYYY

## 통화 감지 규칙 (매우 중요!)
영수증의 언어, 통화 기호, 국가 정보를 종합하여 통화를 정확히 판별하세요:

| 기호/단서 | 통화 코드 |
|-----------|-----------|
| ¥, 円, 엔, 일본어 텍스트 | JPY |
| ₩, 원, 한국어 텍스트 | KRW |
| $, USD, 영어(미국) | USD |
| ¥, 元, 人民币, 중국어 간체 | CNY |
| €, EUR, 유럽 언어 | EUR |
| HK$, HKD, 港幣 | HKD |
| £, GBP | GBP |
| A$, AUD | AUD |
| C$, CAD | CAD |
| CHF, Fr. (스위스) | CHF |
| S$, SGD | SGD |
| ฿, THB, 태국어 | THB |
| NT$, TWD | TWD |
| ₫, VND, 베트남어 | VND |
| ₱, PHP | PHP |

**중요**: ¥ 기호는 JPY와 CNY 모두 사용합니다. 텍스트 언어(일본어 vs 중국어)로 구분하세요.

## 금액 인식
- 일본: ¥, 円 → 合計, お支払い 근처 금액
- 한국: ₩, 원 → 합계 근처 금액
- 미국/영어: $, Total 근처 금액
- 중국: ¥, 元 → 合计, 总计 근처 금액
- 유럽: €, Total, Summe, Totale 근처 금액
- 홍콩: HK$, 總計 근처 금액

## 가게 유형 판별
- コンビニ, ローソン, セブン, ファミマ, 便利店 → 음료/간식
- レストラン, 食堂, 居酒屋, 餐厅, Restaurant → 식사비
- ホテル, 旅館, 宿泊, 酒店, Hotel → 숙박비
- JR, 電車, バス, タクシー, Suica, PASMO, 地铁, Taxi, Uber → 교통비

## 가게명 표기 규칙 (매우 중요!)
- 일본어 영수증: 가게명을 일본어 원문 그대로 표기 (예: アパホテル, ローソン, セブンイレブン)
- 중국어 영수증: 가게명을 중국어 원문 그대로 표기
- 영어 영수증: 영어 원문 그대로 표기
- 한국어로 번역하지 마세요! 원문 유지!

이 영수증 이미지를 분석해주세요.
이미지의 모든 텍스트를 주의 깊게 읽고, 특히 날짜와 금액을 정확히 파악해주세요.

## 응답 형식 (JSON)
```json
{
    "date": "YYYY-MM-DD",
    "amount": 숫자,
    "currency": "통화코드 (KRW/JPY/USD/CNY/EUR/HKD/GBP/AUD/CAD/CHF/SGD/THB/TWD/VND/PHP)",
    "payment_method": "현금" 또는 "신용카드",
    "category": "교통비" 또는 "식사비" 또는 "음료/간식" 또는 "숙박비" 또는 "기타",
    "description": "가게명 (원문 그대로)",
    "detected_language": "감지된 언어",
    "raw_date_text": "영수증에 표시된 원본 날짜 텍스트"
}
```

## 주의사항
- 날짜: 영수증에 적힌 날짜를 정확히 읽고 YYYY-MM-DD로 변환
- 일본 연호(令和, 平成 등)는 서력으로 변환
- 금액: 합계/Total/お支払い/合计 금액 사용
- 통화: 기호와 언어를 종합 판단하여 정확한 통화 코드 사용
- **description (가게명)**: 원문 그대로 표기! 한국어로 번역하지 마세요!

JSON만 반환해주세요."""

        response = model.generate_content([prompt, img])
        
        result_text = response.text.strip()
        logger.info(f"Gemini 응답 수신: {result_text[:100]}...")
        
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', result_text)
        if json_match:
            result_text = json_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
        
        parsed_result = json.loads(result_text)
        
        date_str = parsed_result.get('date', datetime.now().strftime('%Y-%m-%d'))
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"잘못된 날짜 형식: {date_str}, 오늘 날짜로 대체")
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        raw_date = parsed_result.get('raw_date_text', '')
        detected_lang = parsed_result.get('detected_language', '')
        if raw_date:
            logger.info(f"원본 날짜 텍스트: {raw_date}")
        if detected_lang:
            logger.info(f"감지된 언어: {detected_lang}")
        
        return {
            'success': True,
            'error': None,
            'data': {
                'date': date_str,
                'amount': float(parsed_result.get('amount', 0)),
                'currency': parsed_result.get('currency', 'JPY'),
                'payment_method': parsed_result.get('payment_method', '현금'),
                'category': parsed_result.get('category', '기타'),
                'description': parsed_result.get('description', ''),
                'detected_language': detected_lang,
                'raw_date_text': raw_date
            }
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {str(e)}")
        return {
            'success': False,
            'error': f'JSON 파싱 오류: {str(e)}',
            'data': None
        }
    except FileNotFoundError as e:
        logger.error(f"파일을 찾을 수 없음: {str(e)}")
        return {
            'success': False,
            'error': '업로드된 이미지 파일을 찾을 수 없습니다.',
            'data': None
        }
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        logger.error(f"영수증 분석 오류: {error_type}: {error_msg}")
        
        if 'API_KEY_INVALID' in error_msg or 'PERMISSION_DENIED' in error_msg:
            return {
                'success': False,
                'error': 'Google API 키가 유효하지 않습니다. API 키를 확인해주세요.',
                'data': None
            }
        if 'RESOURCE_EXHAUSTED' in error_msg or 'quota' in error_msg.lower():
            return {
                'success': False,
                'error': 'Google API 요청 한도가 초과되었습니다. 잠시 후 다시 시도해주세요.',
                'data': None
            }
        
        return {
            'success': False,
            'error': f'영수증 분석 오류: {error_type}: {error_msg}',
            'data': None
        }


def calculate_krw_amount(amount: float, currency: str, payment_method: str) -> tuple[float, float]:
    """
    원화 환산액을 계산합니다.
    신용카드 결제 시 설정된 수수료율을 추가합니다.
    Returns (krw_amount, exchange_rate)
    """
    from services.database import load_settings
    
    settings = load_settings()
    exchange_rates = settings.get('exchange_rates', Config.EXCHANGE_RATES)
    credit_card_fee_rate = settings.get('credit_card_fee_rate', 2.5) / 100.0
    
    exchange_rate = exchange_rates.get(currency, 1.0)
    krw_amount = amount * exchange_rate
    
    if payment_method == '신용카드':
        krw_amount *= (1 + credit_card_fee_rate)
    
    return round(krw_amount), exchange_rate
