import base64
import re
import json
import logging
from datetime import datetime
from typing import Optional
import openai
from config import Config

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_openai_api_key() -> str:
    """
    OpenAI API 키를 가져옵니다.
    1. Config에서 먼저 확인 (환경변수 또는 런타임 설정)
    2. 없으면 settings 파일에서 확인
    """
    if Config.OPENAI_API_KEY:
        return Config.OPENAI_API_KEY
    
    # settings 파일에서 API 키 확인
    from services.database import load_settings
    settings = load_settings()
    api_key = settings.get('openai_api_key', '')
    
    if api_key:
        # Config에도 설정하여 다음 호출 시 빠르게 접근
        Config.OPENAI_API_KEY = api_key
    
    return api_key


def analyze_receipt_with_gpt(image_path: str) -> dict:
    """
    GPT-4 Vision을 사용하여 영수증을 분석합니다.
    일본어, 한국어, 영어 영수증을 지원합니다.
    """
    logger.info(f"영수증 분석 시작: {image_path}")
    
    api_key = get_openai_api_key()
    
    if not api_key:
        logger.error("OpenAI API 키가 설정되지 않았습니다.")
        return {
            'success': False,
            'error': 'OpenAI API 키가 설정되지 않았습니다. 설정에서 OpenAI API Key를 입력해주세요.',
            'data': None
        }
    
    try:
        # 이미지를 base64로 인코딩
        with open(image_path, 'rb') as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # 이미지 확장자 확인
        extension = image_path.lower().split('.')[-1]
        mime_type = 'image/jpeg' if extension in ['jpg', 'jpeg'] else f'image/{extension}'
        
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 다국어 영수증 OCR 분석 전문가입니다.

## 전문 분야
- 일본어 (日本語) 영수증 분석 - 가장 중요!
- 한국어 영수증 분석
- 영어 영수증 분석

## 날짜 형식 인식
일본 영수증의 다양한 날짜 형식을 정확히 인식하세요:
- 西暦: 2024年1月18日, 2024/01/18, 24.01.18
- 令和: R6年1月18日, 令和6年1月18日 → 2024-01-18
- 平成: H31年4月30日, 平成31年4月30日 → 2019-04-30

## 금액 인식
- 일본: ¥, 円, 엔 표시 확인
- 한국: ₩, 원 표시 확인
- 合計, 합계, Total, お支払い 등의 단어 근처 금액이 총액

## 가게 유형 판별
- コンビニ, ローソン, セブン, ファミマ → 음료/간식
- レストラン, 食堂, 居酒屋 → 식사비
- ホテル, 旅館, 宿泊 → 숙박비
- JR, 電車, バス, タクシー, Suica, PASMO → 교통비

## 가게명 표기 규칙 (매우 중요!)
- 일본어 영수증: 가게명을 일본어 원문 그대로 표기 (예: アパホテル, ローソン, セブンイレブン)
- 한자가 있으면 일본어 읽기로 표기 (예: 東京駅 → 도쿄에키 또는 東京駅 그대로)
- 한국어로 번역하지 마세요! 원문 유지!

이미지를 꼼꼼히 분석하여 모든 텍스트를 정확히 읽어주세요."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """이 영수증 이미지를 분석해주세요. 
이미지의 모든 텍스트를 주의 깊게 읽고, 특히 날짜와 금액을 정확히 파악해주세요.

## 응답 형식 (JSON)
```json
{
    "date": "YYYY-MM-DD",
    "amount": 숫자,
    "currency": "KRW" 또는 "JPY" 또는 "USD",
    "payment_method": "현금" 또는 "신용카드",
    "category": "교통비" 또는 "식사비" 또는 "음료/간식" 또는 "숙박비" 또는 "기타",
    "description": "가게명 (원문 그대로)",
    "detected_language": "일본어" 또는 "한국어" 또는 "영어",
    "raw_date_text": "영수증에 표시된 원본 날짜 텍스트"
}
```

## 주의사항
- 날짜: 영수증에 적힌 날짜를 정확히 읽고 YYYY-MM-DD로 변환
- 일본 연호(令和, 平成 등)는 서력으로 변환
- 금액: 合計/Total/お支払い 금액 사용
- 엔화(¥, 円)가 보이면 currency는 반드시 "JPY"
- **description (가게명)**: 일본어 원문 그대로 표기! 번역하지 마세요!
  - 예: アパホテル, ローソン, セブンイレブン, 東京駅
  - 한국어 번역 금지! (아파호텔 ❌ → アパホテル ✓)

JSON만 반환해주세요."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800
        )
        
        # GPT 응답 파싱
        result_text = response.choices[0].message.content.strip()
        logger.info(f"GPT 응답 수신: {result_text[:100]}...")
        
        # JSON 블록 추출 (```json ... ``` 형식 처리)
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', result_text)
        if json_match:
            result_text = json_match.group(1)
        else:
            # { } 블록만 추출
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
        
        parsed_result = json.loads(result_text)
        
        # 날짜 유효성 검증 및 보정
        date_str = parsed_result.get('date', datetime.now().strftime('%Y-%m-%d'))
        try:
            # 날짜 형식 검증
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"잘못된 날짜 형식: {date_str}, 오늘 날짜로 대체")
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        # 로그에 상세 정보 출력
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
                'currency': parsed_result.get('currency', 'JPY'),  # 기본값을 JPY로 변경 (일본 여행)
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
    except openai.AuthenticationError as e:
        logger.error(f"OpenAI 인증 오류: {str(e)}")
        return {
            'success': False,
            'error': 'OpenAI API 키가 유효하지 않습니다. API 키를 확인해주세요.',
            'data': None
        }
    except openai.RateLimitError as e:
        logger.error(f"OpenAI API 한도 초과: {str(e)}")
        return {
            'success': False,
            'error': 'OpenAI API 요청 한도가 초과되었습니다. 잠시 후 다시 시도해주세요.',
            'data': None
        }
    except openai.APIConnectionError as e:
        logger.error(f"OpenAI API 연결 오류: {str(e)}")
        return {
            'success': False,
            'error': 'OpenAI API에 연결할 수 없습니다. 네트워크를 확인해주세요.',
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
        logger.error(f"영수증 분석 오류: {type(e).__name__}: {str(e)}")
        return {
            'success': False,
            'error': f'영수증 분석 오류: {type(e).__name__}: {str(e)}',
            'data': None
        }


def calculate_krw_amount(amount: float, currency: str, payment_method: str) -> float:
    """
    원화 환산액을 계산합니다.
    신용카드 결제 시 설정된 수수료율을 추가합니다.
    """
    from services.database import load_settings
    
    settings = load_settings()
    exchange_rates = settings.get('exchange_rates', Config.EXCHANGE_RATES)
    credit_card_fee_rate = settings.get('credit_card_fee_rate', 2.5) / 100.0  # 퍼센트를 비율로 변환
    
    exchange_rate = exchange_rates.get(currency, 1.0)
    krw_amount = amount * exchange_rate
    
    # 신용카드 결제 시 수수료 추가
    if payment_method == '신용카드':
        krw_amount *= (1 + credit_card_fee_rate)
    
    return round(krw_amount)
