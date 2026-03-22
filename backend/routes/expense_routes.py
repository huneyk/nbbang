import os
import io
import uuid
import logging
import tempfile
from datetime import datetime
from flask import Blueprint, request, jsonify, make_response
from werkzeug.utils import secure_filename
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Spacer, Table, TableStyle, Paragraph, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
from config import Config
from models.expense import Expense
from services.ocr_service import analyze_receipt_with_gemini, calculate_krw_amount
from services.database import (
    get_database, load_settings, save_settings,
    list_trips, archive_current_trip, create_new_trip, load_trip, delete_trip
)
from services.image_service import (
    get_image_info,
    fix_orientation_only, crop_receipt, downsize_for_storage
)
from services.receipt_storage import (
    save_receipt as save_receipt_to_gridfs,
    get_receipt as get_receipt_from_gridfs
)

logger = logging.getLogger(__name__)

expense_bp = Blueprint('expense', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@expense_bp.route('/api/upload-receipt', methods=['POST'])
def upload_receipt():
    """영수증 이미지를 업로드하고 자동 crop → downsize → OCR 분석 → GridFS 저장을 수행합니다."""
    if 'receipt' not in request.files:
        return jsonify({'success': False, 'error': '파일이 없습니다.'}), 400

    file = request.files['receipt']

    if file.filename == '':
        return jsonify({'success': False, 'error': '파일이 선택되지 않았습니다.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '지원하지 않는 파일 형식입니다.'}), 400

    upload_folder = Config.UPLOAD_FOLDER
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    base_name = os.path.splitext(filename)[0]
    base_id = str(uuid.uuid4())

    temp_path = os.path.join(upload_folder, f"temp_{base_id}")
    oriented_path = os.path.join(upload_folder, f"oriented_{base_id}.jpg")
    cropped_path = os.path.join(upload_folder, f"cropped_{base_id}.jpg")
    storage_path = os.path.join(upload_folder, f"storage_{base_id}.jpg")

    temp_files = [temp_path, oriented_path, cropped_path, storage_path]

    file.save(temp_path)

    try:
        original_info = get_image_info(temp_path)
        if original_info:
            logger.info(f"원본 이미지: {original_info['width']}x{original_info['height']}, "
                       f"{original_info['file_size_kb']}KB")

        # 1) EXIF 방향 보정
        fix_orientation_only(temp_path, oriented_path)

        # 2) 영수증 영역 자동 crop
        is_cropped = crop_receipt(oriented_path, cropped_path)
        logger.info(f"영수증 자동 crop: {'성공' if is_cropped else '윤곽 미감지 (원본 사용)'}")

        # 3) 저장용 다운사이즈 (max 1500px, max 500KB)
        downsize_for_storage(cropped_path, storage_path)

        # 4) Gemini OCR 분석 (다운사이즈된 이미지 사용)
        result = analyze_receipt_with_gemini(storage_path)

        # 5) MongoDB GridFS에 저장
        storage_filename = f"{base_id}_{base_name}.jpg"
        receipt_id = save_receipt_to_gridfs(storage_path, storage_filename)

        if result['success']:
            result['data']['receipt_image'] = receipt_id

        return jsonify(result)

    except Exception as e:
        logger.error(f"영수증 처리 오류: {str(e)}")
        return jsonify({'success': False, 'error': f'영수증 처리에 실패했습니다: {str(e)}'}), 500

    finally:
        for p in temp_files:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


@expense_bp.route('/api/receipts/<receipt_id>/image', methods=['GET'])
def get_receipt_image(receipt_id: str):
    """GridFS에서 영수증 이미지를 서빙합니다."""
    grid_out = get_receipt_from_gridfs(receipt_id)
    if grid_out is None:
        return jsonify({'success': False, 'error': '영수증 이미지를 찾을 수 없습니다.'}), 404

    response = make_response(grid_out.read())
    response.headers['Content-Type'] = grid_out.content_type or 'image/jpeg'
    response.headers['Content-Disposition'] = f'inline; filename="{grid_out.filename}"'
    response.headers['Cache-Control'] = 'public, max-age=31536000'
    return response


@expense_bp.route('/api/expenses', methods=['GET'])
def get_expenses():
    """모든 경비 내역을 조회합니다."""
    db = get_database()
    expenses = list(db.expenses.find().sort('created_at', -1))
    
    return jsonify({
        'success': True,
        'data': expenses
    })


@expense_bp.route('/api/expenses', methods=['POST'])
def create_expense():
    """새 경비를 등록합니다."""
    data = request.json
    
    # 필수 필드 검증
    required_fields = ['date', 'category', 'amount', 'currency', 'payment_method', 'payer']
    for field in required_fields:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} 필드가 필요합니다.'}), 400
    
    # 개인 지출 여부 확인
    is_personal_expense = data.get('is_personal_expense', False)
    personal_expense_for = data.get('personal_expense_for') if is_personal_expense else None
    
    # 개인 지출인 경우 해당자 필수 검증
    if is_personal_expense and not personal_expense_for:
        return jsonify({'success': False, 'error': '개인 지출 해당자를 선택해주세요.'}), 400
    
    # 원화 환산액 계산
    krw_amount, exchange_rate = calculate_krw_amount(
        float(data['amount']),
        data['currency'],
        data['payment_method']
    )
    
    expense = Expense(
        date=data['date'],
        category=data['category'],
        amount=float(data['amount']),
        currency=data['currency'],
        payment_method=data['payment_method'],
        krw_amount=krw_amount,
        description=data.get('description', ''),
        payer=data['payer'],
        receipt_image=data.get('receipt_image'),
        is_personal_expense=is_personal_expense,
        personal_expense_for=personal_expense_for,
        exchange_rate=exchange_rate
    )
    
    db = get_database()
    result = db.expenses.insert_one(expense.to_dict())
    
    expense_dict = expense.to_dict()
    expense_dict['_id'] = str(result.inserted_id)
    
    return jsonify({
        'success': True,
        'data': expense_dict
    }), 201


@expense_bp.route('/api/expenses/<expense_id>', methods=['DELETE'])
def delete_expense(expense_id: str):
    """경비를 삭제합니다."""
    try:
        db = get_database()
        result = db.expenses.delete_one({'_id': expense_id})
        
        if result.deleted_count == 0:
            return jsonify({'success': False, 'error': '경비를 찾을 수 없습니다.'}), 404
        
        return jsonify({'success': True, 'message': '삭제되었습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@expense_bp.route('/api/summary', methods=['GET'])
def get_summary():
    """경비 요약 및 분담금을 계산합니다."""
    db = get_database()
    expenses = list(db.expenses.find())
    settings = load_settings()
    
    participants = settings.get('participants', [])
    categories = settings.get('categories', [])
    
    # 공동 경비와 개인 지출 분리
    shared_expenses = [exp for exp in expenses if not exp.get('is_personal_expense', False)]
    personal_expenses = [exp for exp in expenses if exp.get('is_personal_expense', False)]
    
    # 총 비용 (전체: 공동 + 개인)
    total_krw = sum(exp.get('krw_amount', 0) for exp in expenses)
    
    # 공동 경비 총액 (1인당 분담 계산용)
    shared_total_krw = sum(exp.get('krw_amount', 0) for exp in shared_expenses)
    
    # 개인 지출 총액
    personal_total_krw = sum(exp.get('krw_amount', 0) for exp in personal_expenses)
    
    # 참가자별 지불액 (공동 경비만)
    payer_totals = {payer: 0 for payer in participants}
    for exp in shared_expenses:
        payer = exp.get('payer', '')
        if payer in payer_totals:
            payer_totals[payer] += exp.get('krw_amount', 0)
    
    # 참가자별 개인 지출 (다른 사람이 대신 결제해준 개인 지출)
    personal_expense_totals = {person: 0 for person in participants}
    personal_expense_details = {person: [] for person in participants}
    
    for exp in personal_expenses:
        person_for = exp.get('personal_expense_for', '')
        if person_for in personal_expense_totals:
            personal_expense_totals[person_for] += exp.get('krw_amount', 0)
            personal_expense_details[person_for].append({
                'date': exp.get('date', ''),
                'description': exp.get('description', ''),
                'amount': exp.get('krw_amount', 0),
                'payer': exp.get('payer', ''),
                'category': exp.get('category', '')
            })
    
    # 참가자별 개인 지출을 대신 결제해준 금액
    paid_for_others = {payer: 0 for payer in participants}
    for exp in personal_expenses:
        payer = exp.get('payer', '')
        if payer in paid_for_others:
            paid_for_others[payer] += exp.get('krw_amount', 0)
    
    # 1인당 분담액 (공동 경비만 기준)
    num_participants = len(participants)
    per_person = round(shared_total_krw / num_participants) if num_participants > 0 else 0
    
    # 정산 내역 (누가 얼마를 받거나 내야 하는지)
    # 공동 경비 정산 + 개인 지출 정산
    settlements = {}
    for payer in participants:
        paid = payer_totals[payer]  # 공동 경비 지불액
        paid_for_other = paid_for_others[payer]  # 다른 사람 개인 지출 대신 결제액
        personal_expense = personal_expense_totals[payer]  # 본인 개인 지출 총액
        
        # 공동 경비 기준 차액
        shared_diff = per_person - paid
        
        # 최종 정산액 = 공동 경비 정산 + 개인 지출 - 대신 결제해준 금액
        final_diff = shared_diff + personal_expense - paid_for_other
        
        settlements[payer] = {
            'paid': round(paid),  # 공동 경비 지불액
            'paid_for_others': round(paid_for_other),  # 타인 개인 지출 대신 결제액
            'should_pay': per_person,  # 1인당 공동 경비 분담액
            'personal_expense': round(personal_expense),  # 본인 개인 지출 총액
            'personal_expense_details': personal_expense_details[payer],  # 개인 지출 상세
            'shared_difference': round(shared_diff),  # 공동 경비 정산액
            'difference': round(final_diff),  # 최종 정산액
            'status': '내야 할 금액' if final_diff > 0 else ('받을 금액' if final_diff < 0 else '정산 완료')
        }
    
    # 카테고리별 지출 (전체)
    category_totals = {cat: 0 for cat in categories}
    for exp in expenses:
        category = exp.get('category', '기타')
        if category in category_totals:
            category_totals[category] += exp.get('krw_amount', 0)
    
    return jsonify({
        'success': True,
        'data': {
            'total_krw': round(total_krw),
            'shared_total_krw': round(shared_total_krw),
            'personal_total_krw': round(personal_total_krw),
            'per_person': per_person,
            'num_participants': num_participants,
            'payer_totals': {k: round(v) for k, v in payer_totals.items()},
            'settlements': settlements,
            'category_totals': {k: round(v) for k, v in category_totals.items()},
            'expense_count': len(expenses),
            'shared_expense_count': len(shared_expenses),
            'personal_expense_count': len(personal_expenses)
        }
    })


@expense_bp.route('/api/config', methods=['GET'])
def get_config():
    """설정 정보를 반환합니다."""
    settings = load_settings()
    currencies = settings.get('currencies', [
        {'code': 'KRW', 'name': '원', 'flag': '🇰🇷', 'rate': 1.0, 'is_base': True},
        {'code': 'USD', 'name': '달러', 'flag': '🇺🇸', 'rate': 1350.0, 'is_base': False},
        {'code': 'JPY', 'name': '엔', 'flag': '🇯🇵', 'rate': 9.5, 'is_base': False},
        {'code': 'CNY', 'name': '위안', 'flag': '🇨🇳', 'rate': 185.0, 'is_base': False},
        {'code': 'EUR', 'name': '유로', 'flag': '🇪🇺', 'rate': 1480.0, 'is_base': False},
        {'code': 'HKD', 'name': '홍콩달러', 'flag': '🇭🇰', 'rate': 173.0, 'is_base': False},
    ])
    return jsonify({
        'success': True,
        'data': {
            'trip_title': settings.get('trip_title', '여행 경비 정산'),
            'participants': settings.get('participants', []),
            'categories': settings.get('categories', []),
            'currencies': currencies,
            'exchange_rates': settings.get('exchange_rates', {'KRW': 1.0, 'USD': 1350.0, 'JPY': 9.5}),
            'credit_card_fee_rate': settings.get('credit_card_fee_rate', 2.5),
            'exchange_rate_info': settings.get('exchange_rate_info', {}),
        }
    })


@expense_bp.route('/api/exchange-rates', methods=['PUT'])
def update_exchange_rates():
    """환율을 업데이트합니다."""
    data = request.json
    settings = load_settings()
    
    exchange_rates = settings.get('exchange_rates', {'KRW': 1.0, 'JPY': 9.5, 'USD': 1350.0})
    currencies = settings.get('currencies', [])
    
    # 개별 통화 환율 업데이트
    for currency_code, rate in data.items():
        exchange_rates[currency_code] = float(rate)
        Config.EXCHANGE_RATES[currency_code] = float(rate)
        # currencies 배열도 동기화
        for curr in currencies:
            if curr['code'] == currency_code:
                curr['rate'] = float(rate)
                break
    
    settings['exchange_rates'] = exchange_rates
    settings['currencies'] = currencies
    save_settings(settings)
    
    return jsonify({
        'success': True,
        'data': exchange_rates
    })


@expense_bp.route('/api/exchange-rates/fetch', methods=['POST'])
def fetch_latest_exchange_rates():
    """최신 환율을 수동으로 가져옵니다 (현찰살때 기준)."""
    from services.exchange_rate_service import fetch_exchange_rates, apply_fetched_rates

    settings = load_settings()
    result = fetch_exchange_rates(settings)

    if not result.get('rates'):
        return jsonify({
            'success': False,
            'error': '환율 조회에 실패했습니다. 잠시 후 다시 시도해주세요.'
        }), 502

    updated = apply_fetched_rates(settings, result)
    save_settings(updated)

    return jsonify({
        'success': True,
        'data': {
            'rates': result['rates'],
            'source': result['source'],
            'updated_at': result['updated_at'],
            'rate_type': result['rate_type'],
            'currencies': updated.get('currencies', []),
        }
    })


@expense_bp.route('/api/exchange-rates/info', methods=['GET'])
def get_exchange_rate_info():
    """마지막 환율 갱신 정보를 반환합니다."""
    settings = load_settings()
    info = settings.get('exchange_rate_info', {})
    return jsonify({
        'success': True,
        'data': info
    })


# ===== 통화 관리 API =====

@expense_bp.route('/api/currencies', methods=['GET'])
def get_currencies():
    """모든 통화 목록을 반환합니다. 기본 5개 통화가 항상 포함됩니다."""
    from services.exchange_rate_service import CURRENCY_INFO, DEFAULT_FETCH_CURRENCIES
    from services.database import DEFAULT_SETTINGS

    settings = load_settings()
    currencies = settings.get('currencies', list(DEFAULT_SETTINGS['currencies']))

    existing_codes = {c['code'] for c in currencies}
    default_rates = DEFAULT_SETTINGS.get('exchange_rates', {})
    added = False

    for code in DEFAULT_FETCH_CURRENCIES:
        if code not in existing_codes:
            info = CURRENCY_INFO.get(code, {'name': code, 'flag': '🏳️'})
            currencies.append({
                'code': code,
                'name': info['name'],
                'flag': info['flag'],
                'rate': default_rates.get(code, 1.0),
                'is_base': False,
            })
            added = True

    if added:
        settings['currencies'] = currencies
        save_settings(settings)

    return jsonify({
        'success': True,
        'data': currencies
    })


@expense_bp.route('/api/currencies', methods=['POST'])
def add_currency():
    """새 통화를 추가합니다."""
    data = request.json
    
    # 필수 필드 검증
    if not data.get('code') or not data.get('name'):
        return jsonify({'success': False, 'error': '통화 코드와 이름은 필수입니다.'}), 400
    
    code = data['code'].upper().strip()
    name = data['name'].strip()
    flag = data.get('flag', '🏳️').strip()
    rate = float(data.get('rate', 1.0))
    
    settings = load_settings()
    currencies = settings.get('currencies', [])
    exchange_rates = settings.get('exchange_rates', {'KRW': 1.0})
    
    # 중복 검사
    if any(c['code'] == code for c in currencies):
        return jsonify({'success': False, 'error': f'통화 코드 {code}가 이미 존재합니다.'}), 400
    
    # 새 통화 추가
    new_currency = {
        'code': code,
        'name': name,
        'flag': flag,
        'rate': rate,
        'is_base': False
    }
    currencies.append(new_currency)
    
    # exchange_rates도 동기화
    exchange_rates[code] = rate
    Config.EXCHANGE_RATES[code] = rate
    
    settings['currencies'] = currencies
    settings['exchange_rates'] = exchange_rates
    save_settings(settings)
    
    return jsonify({
        'success': True,
        'data': new_currency
    }), 201


@expense_bp.route('/api/currencies/<currency_code>', methods=['PUT'])
def update_currency(currency_code: str):
    """통화 정보를 수정합니다."""
    data = request.json
    settings = load_settings()
    currencies = settings.get('currencies', [])
    exchange_rates = settings.get('exchange_rates', {})
    
    # 통화 찾기
    currency = None
    for c in currencies:
        if c['code'] == currency_code.upper():
            currency = c
            break
    
    if not currency:
        return jsonify({'success': False, 'error': '통화를 찾을 수 없습니다.'}), 404
    
    # 기준 통화(KRW) 환율은 변경 불가
    if currency.get('is_base') and 'rate' in data and float(data['rate']) != 1.0:
        return jsonify({'success': False, 'error': '기준 통화의 환율은 변경할 수 없습니다.'}), 400
    
    # 업데이트
    if 'name' in data:
        currency['name'] = data['name'].strip()
    if 'flag' in data:
        currency['flag'] = data['flag'].strip()
    if 'rate' in data and not currency.get('is_base'):
        currency['rate'] = float(data['rate'])
        exchange_rates[currency_code.upper()] = float(data['rate'])
        Config.EXCHANGE_RATES[currency_code.upper()] = float(data['rate'])
    
    settings['currencies'] = currencies
    settings['exchange_rates'] = exchange_rates
    save_settings(settings)
    
    return jsonify({
        'success': True,
        'data': currency
    })


@expense_bp.route('/api/currencies/<currency_code>', methods=['DELETE'])
def delete_currency(currency_code: str):
    """통화를 삭제합니다."""
    settings = load_settings()
    currencies = settings.get('currencies', [])
    exchange_rates = settings.get('exchange_rates', {})
    
    # 통화 찾기
    currency = None
    for c in currencies:
        if c['code'] == currency_code.upper():
            currency = c
            break
    
    if not currency:
        return jsonify({'success': False, 'error': '통화를 찾을 수 없습니다.'}), 404
    
    # 기준 통화는 삭제 불가
    if currency.get('is_base'):
        return jsonify({'success': False, 'error': '기준 통화는 삭제할 수 없습니다.'}), 400
    
    # 삭제
    currencies = [c for c in currencies if c['code'] != currency_code.upper()]
    
    # exchange_rates에서도 삭제
    if currency_code.upper() in exchange_rates:
        del exchange_rates[currency_code.upper()]
    if currency_code.upper() in Config.EXCHANGE_RATES:
        del Config.EXCHANGE_RATES[currency_code.upper()]
    
    settings['currencies'] = currencies
    settings['exchange_rates'] = exchange_rates
    save_settings(settings)
    
    return jsonify({
        'success': True,
        'message': f'{currency_code} 통화가 삭제되었습니다.'
    })


@expense_bp.route('/api/settings', methods=['GET'])
def get_settings():
    """전체 설정을 반환합니다."""
    settings = load_settings()
    return jsonify({
        'success': True,
        'data': settings
    })


@expense_bp.route('/api/settings', methods=['PUT'])
def update_settings():
    """전체 설정을 업데이트합니다."""
    data = request.json
    settings = load_settings()
    
    # 업데이트 가능한 필드들
    if 'trip_title' in data:
        settings['trip_title'] = data['trip_title']
    
    if 'participants' in data:
        # 빈 문자열 제거 및 공백 정리
        participants = [p.strip() for p in data['participants'] if p.strip()]
        settings['participants'] = participants
    
    if 'categories' in data:
        # 빈 문자열 제거 및 공백 정리
        categories = [c.strip() for c in data['categories'] if c.strip()]
        settings['categories'] = categories
    
    if 'credit_card_fee_rate' in data:
        settings['credit_card_fee_rate'] = float(data['credit_card_fee_rate'])
        # Config도 업데이트 (런타임에서 사용)
        Config.CREDIT_CARD_FEE_RATE = float(data['credit_card_fee_rate']) / 100.0
    
    if 'google_api_key' in data:
        settings['google_api_key'] = data['google_api_key']
        Config.GOOGLE_API_KEY = data['google_api_key']
    
    if 'koreaexim_api_key' in data:
        settings['koreaexim_api_key'] = data['koreaexim_api_key']
        Config.KOREAEXIM_API_KEY = data['koreaexim_api_key']
    
    if 'currencies' in data:
        settings['currencies'] = data['currencies']
        # exchange_rates도 동기화
        exchange_rates = {}
        for curr in data['currencies']:
            exchange_rates[curr['code']] = float(curr['rate'])
            Config.EXCHANGE_RATES[curr['code']] = float(curr['rate'])
        settings['exchange_rates'] = exchange_rates
    elif 'exchange_rates' in data:
        settings['exchange_rates'] = data['exchange_rates']
        # Config도 업데이트
        for currency, rate in data['exchange_rates'].items():
            Config.EXCHANGE_RATES[currency] = float(rate)
    
    save_settings(settings)
    
    return jsonify({
        'success': True,
        'data': settings
    })


# ===== 여행 관리 API =====

@expense_bp.route('/api/trips', methods=['GET'])
def get_trips():
    """저장된 모든 여행 목록을 반환합니다."""
    trips = list_trips()
    return jsonify({
        'success': True,
        'data': trips
    })


@expense_bp.route('/api/trips/new', methods=['POST'])
def create_trip():
    """새로운 여행을 생성합니다. 현재 여행은 아카이브됩니다."""
    data = request.json
    
    new_title = data.get('trip_title', '새 여행')
    participants = data.get('participants', [])
    categories = data.get('categories', [])
    credit_card_fee_rate = data.get('credit_card_fee_rate', 2.5)
    
    # 현재 여행 아카이브
    archived_id = archive_current_trip()
    
    # 새 여행 생성
    new_settings = create_new_trip(
        new_title=new_title,
        participants=participants if participants else None,
        categories=categories if categories else None,
        credit_card_fee_rate=credit_card_fee_rate
    )
    
    return jsonify({
        'success': True,
        'data': {
            'archived_trip_id': archived_id,
            'new_settings': new_settings
        }
    }), 201


@expense_bp.route('/api/trips/<trip_id>', methods=['GET'])
def get_trip(trip_id: str):
    """특정 여행을 불러옵니다."""
    # 현재 여행 먼저 아카이브
    archive_current_trip()
    
    # 선택한 여행 불러오기
    result = load_trip(trip_id)
    
    if not result:
        return jsonify({
            'success': False,
            'error': '여행을 찾을 수 없습니다.'
        }), 404
    
    return jsonify({
        'success': True,
        'data': result
    })


@expense_bp.route('/api/trips/<trip_id>', methods=['DELETE'])
def remove_trip(trip_id: str):
    """아카이브된 여행을 삭제합니다."""
    success = delete_trip(trip_id)
    
    if not success:
        return jsonify({
            'success': False,
            'error': '여행을 찾을 수 없습니다.'
        }), 404
    
    return jsonify({
        'success': True,
        'message': '여행이 삭제되었습니다.'
    })


@expense_bp.route('/api/report/download', methods=['GET'])
def download_report():
    """경비 리포트를 Excel 파일로 다운로드합니다."""
    db = get_database()
    expenses = list(db.expenses.find().sort('date', 1))
    settings = load_settings()
    
    participants = settings.get('participants', [])
    categories = settings.get('categories', [])
    trip_title = settings.get('trip_title', '여행 경비 정산')
    
    # 공동 경비와 개인 지출 분리
    shared_expenses = [exp for exp in expenses if not exp.get('is_personal_expense', False)]
    personal_expenses = [exp for exp in expenses if exp.get('is_personal_expense', False)]
    
    # 요약 데이터 계산
    total_krw = sum(exp.get('krw_amount', 0) for exp in expenses)
    shared_total_krw = sum(exp.get('krw_amount', 0) for exp in shared_expenses)
    personal_total_krw = sum(exp.get('krw_amount', 0) for exp in personal_expenses)
    
    # 참가자별 지불액 (공동 경비만)
    payer_totals = {payer: 0 for payer in participants}
    for exp in shared_expenses:
        payer = exp.get('payer', '')
        if payer in payer_totals:
            payer_totals[payer] += exp.get('krw_amount', 0)
    
    # 참가자별 개인 지출
    personal_expense_totals = {person: 0 for person in participants}
    for exp in personal_expenses:
        person_for = exp.get('personal_expense_for', '')
        if person_for in personal_expense_totals:
            personal_expense_totals[person_for] += exp.get('krw_amount', 0)
    
    # 참가자별 타인 개인지출 대납액
    paid_for_others = {payer: 0 for payer in participants}
    for exp in personal_expenses:
        payer = exp.get('payer', '')
        if payer in paid_for_others:
            paid_for_others[payer] += exp.get('krw_amount', 0)
    
    num_participants = len(participants)
    per_person = round(shared_total_krw / num_participants) if num_participants > 0 else 0
    
    settlements = {}
    for payer in participants:
        paid = payer_totals[payer]
        paid_for_other = paid_for_others[payer]
        personal_expense = personal_expense_totals[payer]
        shared_diff = per_person - paid
        final_diff = shared_diff + personal_expense - paid_for_other
        
        settlements[payer] = {
            'paid': round(paid),
            'paid_for_others': round(paid_for_other),
            'should_pay': per_person,
            'personal_expense': round(personal_expense),
            'difference': round(final_diff),
            'status': '내야 할 금액' if final_diff > 0 else ('받을 금액' if final_diff < 0 else '정산 완료')
        }
    
    category_totals = {cat: 0 for cat in categories}
    for exp in expenses:
        category = exp.get('category', '기타')
        if category in category_totals:
            category_totals[category] += exp.get('krw_amount', 0)
    
    # Excel 워크북 생성
    wb = Workbook()
    
    # 스타일 정의
    header_font = Font(bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color='1a1a2e', end_color='1a1a2e', fill_type='solid')
    personal_fill = PatternFill(start_color='fff0f0', end_color='fff0f0', fill_type='solid')
    title_font = Font(bold=True, size=14, color='e94560')
    currency_font = Font(name='Consolas', size=11)
    border = Border(
        left=Side(style='thin', color='cccccc'),
        right=Side(style='thin', color='cccccc'),
        top=Side(style='thin', color='cccccc'),
        bottom=Side(style='thin', color='cccccc')
    )
    center_align = Alignment(horizontal='center', vertical='center')
    right_align = Alignment(horizontal='right', vertical='center')
    
    # === 시트 1: 경비 내역 ===
    ws_expenses = wb.active
    ws_expenses.title = "경비 내역"
    
    # 제목
    ws_expenses.merge_cells('A1:J1')
    ws_expenses['A1'] = f'🌏 {trip_title} - 경비 내역서'
    ws_expenses['A1'].font = Font(bold=True, size=18, color='e94560')
    ws_expenses['A1'].alignment = center_align
    ws_expenses.row_dimensions[1].height = 35
    
    # 생성 날짜
    ws_expenses.merge_cells('A2:J2')
    ws_expenses['A2'] = f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws_expenses['A2'].alignment = center_align
    ws_expenses['A2'].font = Font(size=10, color='666666')
    ws_expenses.row_dimensions[2].height = 20
    
    # 헤더 행
    headers = ['날짜', '지출 항목', '금액', '통화', '결제수단', '적용 환율', '원화 환산액', '세부 내역', '지불한 사람', '지출 유형']
    for col, header in enumerate(headers, 1):
        cell = ws_expenses.cell(row=4, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = border
    ws_expenses.row_dimensions[4].height = 25
    
    # 데이터 행
    for row, exp in enumerate(expenses, 5):
        is_personal = exp.get('is_personal_expense', False)
        
        ws_expenses.cell(row=row, column=1, value=exp.get('date', '')).border = border
        ws_expenses.cell(row=row, column=2, value=exp.get('category', '')).border = border
        
        amount_cell = ws_expenses.cell(row=row, column=3, value=exp.get('amount', 0))
        amount_cell.font = currency_font
        amount_cell.alignment = right_align
        amount_cell.border = border
        amount_cell.number_format = '#,##0'
        
        ws_expenses.cell(row=row, column=4, value=exp.get('currency', '')).border = border
        ws_expenses.cell(row=row, column=4).alignment = center_align
        
        ws_expenses.cell(row=row, column=5, value=exp.get('payment_method', '')).border = border
        ws_expenses.cell(row=row, column=5).alignment = center_align
        
        exchange_rate_val = exp.get('exchange_rate')
        if exchange_rate_val is None and exp.get('amount') and exp.get('krw_amount'):
            exchange_rate_val = round(exp['krw_amount'] / exp['amount'], 2) if exp['amount'] != 0 else None
        rate_cell = ws_expenses.cell(row=row, column=6, value=exchange_rate_val or '')
        rate_cell.font = Font(name='Consolas', size=11)
        rate_cell.alignment = right_align
        rate_cell.border = border
        if exchange_rate_val:
            rate_cell.number_format = '#,##0.00'
        
        krw_cell = ws_expenses.cell(row=row, column=7, value=exp.get('krw_amount', 0))
        krw_cell.font = Font(name='Consolas', size=11, color='ffc300')
        krw_cell.alignment = right_align
        krw_cell.border = border
        krw_cell.number_format = '₩#,##0'
        
        ws_expenses.cell(row=row, column=8, value=exp.get('description', '')).border = border
        ws_expenses.cell(row=row, column=9, value=exp.get('payer', '')).border = border
        
        # 지출 유형
        expense_type = f"개인 ({exp.get('personal_expense_for', '')})" if is_personal else "공동"
        type_cell = ws_expenses.cell(row=row, column=10, value=expense_type)
        type_cell.border = border
        type_cell.alignment = center_align
        if is_personal:
            type_cell.font = Font(color='e94560')
            for c in range(1, 11):
                ws_expenses.cell(row=row, column=c).fill = personal_fill
    
    # 열 너비 조정
    column_widths = [12, 12, 15, 8, 12, 14, 18, 25, 12, 14]
    for i, width in enumerate(column_widths, 1):
        ws_expenses.column_dimensions[get_column_letter(i)].width = width
    
    # === 시트 2: 정산 요약 ===
    ws_summary = wb.create_sheet(title="정산 요약")
    
    # 제목
    ws_summary.merge_cells('A1:F1')
    ws_summary['A1'] = '💰 경비 정산 요약'
    ws_summary['A1'].font = Font(bold=True, size=18, color='e94560')
    ws_summary['A1'].alignment = center_align
    ws_summary.row_dimensions[1].height = 35
    
    # 총 경비
    ws_summary['A3'] = '총 경비'
    ws_summary['A3'].font = Font(bold=True, size=12)
    ws_summary['B3'] = total_krw
    ws_summary['B3'].font = Font(name='Consolas', size=14, bold=True, color='ffc300')
    ws_summary['B3'].number_format = '₩#,##0'
    ws_summary['C3'] = f"({len(expenses)}건)"
    ws_summary['C3'].font = Font(size=10, color='666666')
    
    # 공동 경비
    ws_summary['A4'] = '공동 경비'
    ws_summary['A4'].font = Font(bold=True, size=12)
    ws_summary['B4'] = shared_total_krw
    ws_summary['B4'].font = Font(name='Consolas', size=12, color='00d9a5')
    ws_summary['B4'].number_format = '₩#,##0'
    ws_summary['C4'] = f"({len(shared_expenses)}건)"
    ws_summary['C4'].font = Font(size=10, color='666666')
    
    # 개인 지출
    ws_summary['A5'] = '개인 지출'
    ws_summary['A5'].font = Font(bold=True, size=12)
    ws_summary['B5'] = personal_total_krw
    ws_summary['B5'].font = Font(name='Consolas', size=12, color='e94560')
    ws_summary['B5'].number_format = '₩#,##0'
    ws_summary['C5'] = f"({len(personal_expenses)}건)"
    ws_summary['C5'].font = Font(size=10, color='666666')
    
    # 1인당 분담액
    ws_summary['A6'] = '1인당 분담액 (공동 경비)'
    ws_summary['A6'].font = Font(bold=True, size=12)
    ws_summary['B6'] = per_person
    ws_summary['B6'].font = Font(name='Consolas', size=14, bold=True, color='00d9a5')
    ws_summary['B6'].number_format = '₩#,##0'
    ws_summary['C6'] = f"({num_participants}명 기준)"
    ws_summary['C6'].font = Font(size=10, color='666666')
    
    # 정산 내역 헤더
    ws_summary['A8'] = '💸 정산 내역'
    ws_summary['A8'].font = Font(bold=True, size=14)
    
    settlement_headers = ['이름', '공동 경비 지불', '타인 개인지출 대납', '분담액', '개인 지출', '최종 정산액', '상태']
    for col, header in enumerate(settlement_headers, 1):
        cell = ws_summary.cell(row=9, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = border
    
    # 정산 데이터
    row = 10
    for name, data in settlements.items():
        ws_summary.cell(row=row, column=1, value=name).border = border
        
        paid_cell = ws_summary.cell(row=row, column=2, value=data['paid'])
        paid_cell.number_format = '₩#,##0'
        paid_cell.alignment = right_align
        paid_cell.border = border
        
        paid_for_others_cell = ws_summary.cell(row=row, column=3, value=data['paid_for_others'])
        paid_for_others_cell.number_format = '₩#,##0'
        paid_for_others_cell.alignment = right_align
        paid_for_others_cell.border = border
        
        should_pay_cell = ws_summary.cell(row=row, column=4, value=data['should_pay'])
        should_pay_cell.number_format = '₩#,##0'
        should_pay_cell.alignment = right_align
        should_pay_cell.border = border
        
        personal_cell = ws_summary.cell(row=row, column=5, value=data['personal_expense'])
        personal_cell.number_format = '₩#,##0'
        personal_cell.alignment = right_align
        personal_cell.border = border
        if data['personal_expense'] > 0:
            personal_cell.font = Font(color='e94560')
        
        diff_cell = ws_summary.cell(row=row, column=6, value=data['difference'])
        diff_cell.number_format = '₩#,##0'
        diff_cell.alignment = right_align
        diff_cell.border = border
        if data['difference'] > 0:
            diff_cell.font = Font(color='e94560', bold=True)
        elif data['difference'] < 0:
            diff_cell.font = Font(color='00d9a5', bold=True)
        
        status_cell = ws_summary.cell(row=row, column=7, value=data['status'])
        status_cell.alignment = center_align
        status_cell.border = border
        row += 1
    
    # 카테고리별 지출 헤더
    cat_start_row = row + 2
    ws_summary.cell(row=cat_start_row, column=1, value='📊 카테고리별 지출').font = Font(bold=True, size=14)
    
    cat_headers = ['카테고리', '금액', '비율']
    for col, header in enumerate(cat_headers, 1):
        cell = ws_summary.cell(row=cat_start_row + 1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = border
    
    # 카테고리 데이터 (금액 순 정렬)
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    row = cat_start_row + 2
    for category, amount in sorted_categories:
        if amount > 0:
            ws_summary.cell(row=row, column=1, value=category).border = border
            
            amount_cell = ws_summary.cell(row=row, column=2, value=amount)
            amount_cell.number_format = '₩#,##0'
            amount_cell.alignment = right_align
            amount_cell.border = border
            
            pct = (amount / total_krw * 100) if total_krw > 0 else 0
            pct_cell = ws_summary.cell(row=row, column=3, value=pct / 100)
            pct_cell.number_format = '0.0%'
            pct_cell.alignment = center_align
            pct_cell.border = border
            row += 1
    
    # 열 너비 조정
    ws_summary.column_dimensions['A'].width = 20
    ws_summary.column_dimensions['B'].width = 18
    ws_summary.column_dimensions['C'].width = 18
    ws_summary.column_dimensions['D'].width = 15
    ws_summary.column_dimensions['E'].width = 15
    ws_summary.column_dimensions['F'].width = 15
    ws_summary.column_dimensions['G'].width = 12
    
    # 메모리에 저장
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    # 파일명 생성
    filename = f"expense_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Response 생성
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    
    return response


def _register_korean_font():
    """한글 폰트를 등록합니다. macOS/Linux/Windows 순으로 탐색합니다."""
    font_candidates = [
        ('/Library/Fonts/Arial Unicode.ttf', None),
        ('/System/Library/Fonts/Supplemental/AppleGothic.ttf', None),
        ('/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf', None),
        ('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', None),
        ('/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf', None),
        ('C:/Windows/Fonts/malgun.ttf', None),
        ('/System/Library/Fonts/AppleSDGothicNeo.ttc', 0),
    ]
    for path, subfont_idx in font_candidates:
        if not os.path.exists(path):
            continue
        try:
            if subfont_idx is not None:
                pdfmetrics.registerFont(TTFont('Korean', path, subfontIndex=subfont_idx))
            else:
                pdfmetrics.registerFont(TTFont('Korean', path))
            logger.info(f"한글 폰트 등록 성공: {path}")
            return 'Korean'
        except Exception as e:
            logger.warning(f"폰트 로드 실패 ({path}): {e}")
            continue
    logger.error("한글 폰트를 찾을 수 없습니다. Helvetica를 사용합니다.")
    return 'Helvetica'


@expense_bp.route('/api/report/download-receipts', methods=['GET'])
def download_receipt_report():
    """모든 경비 내역을 2x5 그리드로 정리하여 PDF로 다운로드합니다.
    각 셀: 왼쪽에 경비 정보 라벨, 오른쪽에 영수증 이미지.
    영수증이 없는 항목은 '영수증 없음'으로 표시됩니다."""
    db = get_database()
    expenses = list(db.expenses.find().sort('date', 1))
    settings = load_settings()
    trip_title = settings.get('trip_title', '여행 경비 정산')

    if not expenses:
        return jsonify({
            'success': False,
            'error': '경비 내역이 없습니다.'
        }), 400

    korean_font = _register_korean_font()
    receipt_count = sum(1 for e in expenses if e.get('receipt_image'))

    page_w, page_h = A4
    margin = 10 * mm
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin

    grid_cols = 2
    rows_per_page = 5
    col_gap = 4 * mm
    row_gap = 2 * mm

    cell_w = (usable_w - col_gap * (grid_cols - 1)) / grid_cols
    title_h = 16 * mm
    cell_h = (usable_h - title_h - row_gap * (rows_per_page - 1)) / rows_per_page

    label_col_w = cell_w * 0.48
    img_col_w = cell_w * 0.52 - 2 * mm

    field_label_style = ParagraphStyle(
        'FieldLabel', fontName=korean_font, fontSize=8,
        leading=10, textColor=HexColor('#2d5016'),
        spaceBefore=0.5 * mm, spaceAfter=0.5 * mm,
    )
    field_value_style = ParagraphStyle(
        'FieldValue', fontName=korean_font, fontSize=7.5,
        leading=9.5, textColor=HexColor('#333333'),
        spaceBefore=0.5 * mm, spaceAfter=0.5 * mm,
    )
    no_receipt_style = ParagraphStyle(
        'NoReceipt', fontName=korean_font, fontSize=9,
        leading=12, textColor=HexColor('#aaaaaa'),
        alignment=1,
    )
    title_style = ParagraphStyle(
        'ReceiptTitle', fontName=korean_font, fontSize=13,
        leading=17, textColor=HexColor('#1a1a2e'),
    )
    subtitle_style = ParagraphStyle(
        'ReceiptSubtitle', fontName=korean_font, fontSize=8,
        leading=11, textColor=HexColor('#888888'),
        spaceAfter=2 * mm,
    )

    field_labels = [
        '날짜', '지출 항목', '금액', '결제수단',
        '적용 환율', '원화 환산액', '세부 내역', '지불한 사람',
    ]

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )

    elements = []
    temp_files = []

    try:
        cells = []
        for exp in expenses:
            receipt_id = exp.get('receipt_image')
            img_path = None

            if receipt_id:
                grid_out = get_receipt_from_gridfs(receipt_id)
                if grid_out is not None:
                    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                    tmp.write(grid_out.read())
                    tmp.flush()
                    tmp.close()
                    temp_files.append(tmp.name)
                    img_path = tmp.name

            date_str = exp.get('date', '')
            category = exp.get('category', '')
            amount_val = exp.get('amount', 0)
            currency = exp.get('currency', 'KRW')
            krw_amount = exp.get('krw_amount', 0)
            description = exp.get('description', '')
            payer = exp.get('payer', '')
            payment_method = exp.get('payment_method', '')

            exchange_rate_val = exp.get('exchange_rate')
            if exchange_rate_val is None and amount_val and krw_amount and amount_val != 0:
                exchange_rate_val = round(krw_amount / amount_val, 2)
            exchange_str = f"{exchange_rate_val:,.2f}" if exchange_rate_val else ''

            amount_str = f"{amount_val:,.0f} {currency}"
            krw_str = f"₩{krw_amount:,.0f}"
            desc_short = description[:15] + ('…' if len(description) > 15 else '') if description else ''

            field_values = [
                date_str, category, amount_str, payment_method,
                exchange_str, krw_str, desc_short, payer,
            ]

            label_rows = []
            for lbl, val in zip(field_labels, field_values):
                label_rows.append([
                    Paragraph(lbl, field_label_style),
                    Paragraph(str(val), field_value_style),
                ])

            inner_h = cell_h - 2 * mm
            row_h = inner_h / len(field_labels)
            label_name_w = label_col_w * 0.48
            label_val_w = label_col_w * 0.52

            info_table = Table(
                label_rows,
                colWidths=[label_name_w, label_val_w],
                rowHeights=[row_h] * len(field_labels),
            )
            info_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 1 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0.5 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))

            if img_path:
                try:
                    pil_img = PILImage.open(img_path)
                    orig_w, orig_h = pil_img.size
                    pil_img.close()
                except Exception:
                    orig_w, orig_h = 300, 400

                scale = min(img_col_w / orig_w, inner_h / orig_h)
                draw_w = orig_w * scale
                draw_h = orig_h * scale
                img_element = RLImage(img_path, width=draw_w, height=draw_h)
            else:
                placeholder = Table(
                    [[Paragraph('영수증 없음', no_receipt_style)]],
                    colWidths=[img_col_w],
                    rowHeights=[inner_h],
                )
                placeholder.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f5f5f5')),
                ]))
                img_element = placeholder

            cell_content = Table(
                [[info_table, img_element]],
                colWidths=[label_col_w, img_col_w],
                rowHeights=[inner_h],
            )
            cell_content.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('BOX', (0, 0), (-1, -1), 0.5, HexColor('#cccccc')),
            ]))
            cells.append(cell_content)

        items_per_page = grid_cols * rows_per_page
        total_pages = (len(cells) + items_per_page - 1) // items_per_page

        for page_idx in range(total_pages):
            if page_idx > 0:
                elements.append(PageBreak())

            elements.append(Paragraph(f'{trip_title} - 영수증 첨부', title_style))
            elements.append(Paragraph(
                f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                f"총 {len(expenses)}건 (영수증 {receipt_count}건)  |  "
                f"페이지 {page_idx + 1}/{total_pages}",
                subtitle_style,
            ))

            start = page_idx * items_per_page
            page_cells = cells[start:start + items_per_page]

            page_grid_rows = []
            for r in range(rows_per_page):
                row_cells = []
                for c in range(grid_cols):
                    idx = r * grid_cols + c
                    if idx < len(page_cells):
                        row_cells.append(page_cells[idx])
                    else:
                        row_cells.append('')
                page_grid_rows.append(row_cells)

            grid_table = Table(
                page_grid_rows,
                colWidths=[cell_w] * grid_cols,
                rowHeights=[cell_h] * rows_per_page,
                hAlign='CENTER',
            )
            grid_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), col_gap / 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), col_gap / 2),
                ('TOPPADDING', (0, 0), (-1, -1), row_gap / 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), row_gap / 2),
            ]))
            elements.append(grid_table)

        doc.build(elements)

    finally:
        for fp in temp_files:
            try:
                os.unlink(fp)
            except OSError:
                pass

    output.seek(0)
    filename = f"receipts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response
