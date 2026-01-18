import os
import io
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from config import Config
from models.expense import Expense
from services.ocr_service import analyze_receipt_with_gpt, calculate_krw_amount
from services.database import get_database
from services.image_service import resize_image, get_image_info

logger = logging.getLogger(__name__)

expense_bp = Blueprint('expense', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@expense_bp.route('/api/upload-receipt', methods=['POST'])
def upload_receipt():
    """영수증 이미지를 업로드하고 OCR 분석을 수행합니다."""
    if 'receipt' not in request.files:
        return jsonify({'success': False, 'error': '파일이 없습니다.'}), 400
    
    file = request.files['receipt']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': '파일이 선택되지 않았습니다.'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '지원하지 않는 파일 형식입니다.'}), 400
    
    # 업로드 폴더 생성
    upload_folder = Config.UPLOAD_FOLDER
    os.makedirs(upload_folder, exist_ok=True)
    
    # 파일 저장 (원본)
    filename = secure_filename(file.filename)
    # 확장자를 jpg로 통일 (리사이즈 후 JPEG로 저장됨)
    base_name = os.path.splitext(filename)[0]
    unique_filename = f"{uuid.uuid4()}_{base_name}.jpg"
    file_path = os.path.join(upload_folder, unique_filename)
    
    # 임시 파일로 먼저 저장
    temp_path = os.path.join(upload_folder, f"temp_{uuid.uuid4()}")
    file.save(temp_path)
    
    try:
        # 원본 이미지 정보 로깅
        original_info = get_image_info(temp_path)
        if original_info:
            logger.info(f"원본 이미지 업로드: {original_info['width']}x{original_info['height']}, "
                       f"{original_info['file_size_kb']}KB")
        
        # 이미지 리사이즈 및 최적화
        resize_image(temp_path, file_path)
        
        # 리사이즈된 이미지 정보 로깅
        resized_info = get_image_info(file_path)
        if resized_info:
            logger.info(f"리사이즈 완료: {resized_info['width']}x{resized_info['height']}, "
                       f"{resized_info['file_size_kb']}KB")
        
        # 임시 파일 삭제
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    except Exception as e:
        logger.error(f"이미지 처리 오류: {str(e)}")
        # 리사이즈 실패 시 원본 사용
        if os.path.exists(temp_path):
            os.rename(temp_path, file_path)
    
    # OCR 분석
    result = analyze_receipt_with_gpt(file_path)
    
    if result['success']:
        result['data']['receipt_image'] = unique_filename
    
    return jsonify(result)


@expense_bp.route('/api/expenses', methods=['GET'])
def get_expenses():
    """모든 경비 내역을 조회합니다."""
    db = get_database()
    expenses = list(db.expenses.find().sort('date', -1))
    
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
    
    # 원화 환산액 계산
    krw_amount = calculate_krw_amount(
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
        receipt_image=data.get('receipt_image')
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
    
    # 총 비용
    total_krw = sum(exp.get('krw_amount', 0) for exp in expenses)
    
    # 참가자별 지불액
    payer_totals = {payer: 0 for payer in Config.PARTICIPANTS}
    for exp in expenses:
        payer = exp.get('payer', '')
        if payer in payer_totals:
            payer_totals[payer] += exp.get('krw_amount', 0)
    
    # 1인당 분담액
    num_participants = len(Config.PARTICIPANTS)
    per_person = round(total_krw / num_participants) if num_participants > 0 else 0
    
    # 정산 내역 (누가 얼마를 받거나 내야 하는지)
    settlements = {}
    for payer, paid in payer_totals.items():
        diff = per_person - paid  # 부호 반전: 1인당 분담액 - 지불한 금액
        settlements[payer] = {
            'paid': round(paid),
            'should_pay': per_person,
            'difference': round(diff),
            'status': '내야 할 금액' if diff > 0 else ('받을 금액' if diff < 0 else '정산 완료')
        }
    
    # 카테고리별 지출
    category_totals = {cat: 0 for cat in Config.EXPENSE_CATEGORIES}
    for exp in expenses:
        category = exp.get('category', '기타')
        if category in category_totals:
            category_totals[category] += exp.get('krw_amount', 0)
    
    return jsonify({
        'success': True,
        'data': {
            'total_krw': round(total_krw),
            'per_person': per_person,
            'num_participants': num_participants,
            'payer_totals': {k: round(v) for k, v in payer_totals.items()},
            'settlements': settlements,
            'category_totals': {k: round(v) for k, v in category_totals.items()},
            'expense_count': len(expenses)
        }
    })


@expense_bp.route('/api/config', methods=['GET'])
def get_config():
    """설정 정보를 반환합니다."""
    return jsonify({
        'success': True,
        'data': {
            'participants': Config.PARTICIPANTS,
            'categories': Config.EXPENSE_CATEGORIES,
            'exchange_rates': Config.EXCHANGE_RATES,
            'credit_card_fee_rate': Config.CREDIT_CARD_FEE_RATE
        }
    })


@expense_bp.route('/api/exchange-rates', methods=['PUT'])
def update_exchange_rates():
    """환율을 업데이트합니다."""
    data = request.json
    
    if 'JPY' in data:
        Config.EXCHANGE_RATES['JPY'] = float(data['JPY'])
    if 'USD' in data:
        Config.EXCHANGE_RATES['USD'] = float(data['USD'])
    
    return jsonify({
        'success': True,
        'data': Config.EXCHANGE_RATES
    })


@expense_bp.route('/api/report/download', methods=['GET'])
def download_report():
    """경비 리포트를 Excel 파일로 다운로드합니다."""
    db = get_database()
    expenses = list(db.expenses.find().sort('date', 1))
    
    # 요약 데이터 계산
    total_krw = sum(exp.get('krw_amount', 0) for exp in expenses)
    
    payer_totals = {payer: 0 for payer in Config.PARTICIPANTS}
    for exp in expenses:
        payer = exp.get('payer', '')
        if payer in payer_totals:
            payer_totals[payer] += exp.get('krw_amount', 0)
    
    num_participants = len(Config.PARTICIPANTS)
    per_person = round(total_krw / num_participants) if num_participants > 0 else 0
    
    settlements = {}
    for payer, paid in payer_totals.items():
        diff = paid - per_person
        settlements[payer] = {
            'paid': round(paid),
            'should_pay': per_person,
            'difference': round(diff),
            'status': '받을 금액' if diff > 0 else ('내야 할 금액' if diff < 0 else '정산 완료')
        }
    
    category_totals = {cat: 0 for cat in Config.EXPENSE_CATEGORIES}
    for exp in expenses:
        category = exp.get('category', '기타')
        if category in category_totals:
            category_totals[category] += exp.get('krw_amount', 0)
    
    # Excel 워크북 생성
    wb = Workbook()
    
    # 스타일 정의
    header_font = Font(bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color='1a1a2e', end_color='1a1a2e', fill_type='solid')
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
    ws_expenses.merge_cells('A1:H1')
    ws_expenses['A1'] = '🌏 여행 경비 내역서'
    ws_expenses['A1'].font = Font(bold=True, size=18, color='e94560')
    ws_expenses['A1'].alignment = center_align
    ws_expenses.row_dimensions[1].height = 35
    
    # 생성 날짜
    ws_expenses.merge_cells('A2:H2')
    ws_expenses['A2'] = f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws_expenses['A2'].alignment = center_align
    ws_expenses['A2'].font = Font(size=10, color='666666')
    ws_expenses.row_dimensions[2].height = 20
    
    # 헤더 행
    headers = ['날짜', '지출 항목', '금액', '통화', '결제수단', '원화 환산액', '세부 내역', '지불한 사람']
    for col, header in enumerate(headers, 1):
        cell = ws_expenses.cell(row=4, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = border
    ws_expenses.row_dimensions[4].height = 25
    
    # 데이터 행
    for row, exp in enumerate(expenses, 5):
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
        
        krw_cell = ws_expenses.cell(row=row, column=6, value=exp.get('krw_amount', 0))
        krw_cell.font = Font(name='Consolas', size=11, color='ffc300')
        krw_cell.alignment = right_align
        krw_cell.border = border
        krw_cell.number_format = '₩#,##0'
        
        ws_expenses.cell(row=row, column=7, value=exp.get('description', '')).border = border
        ws_expenses.cell(row=row, column=8, value=exp.get('payer', '')).border = border
    
    # 열 너비 조정
    column_widths = [12, 12, 15, 8, 12, 18, 25, 12]
    for i, width in enumerate(column_widths, 1):
        ws_expenses.column_dimensions[get_column_letter(i)].width = width
    
    # === 시트 2: 정산 요약 ===
    ws_summary = wb.create_sheet(title="정산 요약")
    
    # 제목
    ws_summary.merge_cells('A1:D1')
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
    
    # 1인당 분담액
    ws_summary['A4'] = '1인당 분담액'
    ws_summary['A4'].font = Font(bold=True, size=12)
    ws_summary['B4'] = per_person
    ws_summary['B4'].font = Font(name='Consolas', size=14, bold=True, color='00d9a5')
    ws_summary['B4'].number_format = '₩#,##0'
    ws_summary['C4'] = f"({num_participants}명 기준)"
    ws_summary['C4'].font = Font(size=10, color='666666')
    
    # 정산 내역 헤더
    ws_summary['A6'] = '💸 정산 내역'
    ws_summary['A6'].font = Font(bold=True, size=14)
    
    settlement_headers = ['이름', '지불한 금액', '분담액', '차액', '상태']
    for col, header in enumerate(settlement_headers, 1):
        cell = ws_summary.cell(row=7, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = border
    
    # 정산 데이터
    row = 8
    for name, data in settlements.items():
        ws_summary.cell(row=row, column=1, value=name).border = border
        
        paid_cell = ws_summary.cell(row=row, column=2, value=data['paid'])
        paid_cell.number_format = '₩#,##0'
        paid_cell.alignment = right_align
        paid_cell.border = border
        
        should_pay_cell = ws_summary.cell(row=row, column=3, value=data['should_pay'])
        should_pay_cell.number_format = '₩#,##0'
        should_pay_cell.alignment = right_align
        should_pay_cell.border = border
        
        diff_cell = ws_summary.cell(row=row, column=4, value=data['difference'])
        diff_cell.number_format = '₩#,##0'
        diff_cell.alignment = right_align
        diff_cell.border = border
        if data['difference'] > 0:
            diff_cell.font = Font(color='00d9a5', bold=True)
        elif data['difference'] < 0:
            diff_cell.font = Font(color='e94560', bold=True)
        
        status_cell = ws_summary.cell(row=row, column=5, value=data['status'])
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
    ws_summary.column_dimensions['A'].width = 15
    ws_summary.column_dimensions['B'].width = 18
    ws_summary.column_dimensions['C'].width = 15
    ws_summary.column_dimensions['D'].width = 15
    ws_summary.column_dimensions['E'].width = 15
    
    # 메모리에 저장
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    # 파일명 생성
    filename = f"여행경비_리포트_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
