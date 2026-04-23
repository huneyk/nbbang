# 🌏 여행 경비 정산 앱

일본어, 한국어, 영어 영수증을 자동으로 분석하여 여행 경비를 정산하는 웹 애플리케이션입니다.

## ✨ 주요 기능

1. **영수증 OCR 분석**: GPT-4 Vision을 사용하여 영수증 이미지에서 자동으로 정보 추출
   - 결제 날짜
   - 금액 및 화폐 단위 (KRW, JPY, USD)
   - 결제 수단 (현금/신용카드)
   - 지출 항목 분류

2. **다국어 영수증 지원**: 일본어, 한국어, 영어 영수증 모두 분석 가능

3. **환율 자동 적용**: 미리 설정된 환율로 원화 환산

4. **해외결제 신용카드 수수료 자동 계산**: 해외 결제 시 사용자가 설정한 수수료율(기본 0%)을 신용카드 결제액에 자동 가산 (KRW 결제 시 미적용)

5. **실시간 경비 정산표**: 
   - 날짜, 지출 항목, 금액, 화폐단위, 결제수단, 원화 환산액, 세부 내역, 지불한 사람

6. **분담금 자동 계산**:
   - 총 비용
   - 1인당 분담액
   - 참가자별 정산 내역 (받을 금액/내야 할 금액)

## 🛠️ 기술 스택

### Backend
- Python 3.12
- Flask 3.0
- MongoDB (pymongo)
- OpenAI GPT-4 Vision API

### Frontend
- React 18
- Axios
- React Dropzone

## 📦 설치 및 실행

### 사전 요구사항
- Python 3.10+
- Node.js 18+
- MongoDB (로컬 또는 Atlas)
- OpenAI API 키

### Backend 설정

```bash
cd backend

# 가상환경 활성화
source ../VENV/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
# .env 파일 생성 후 아래 내용 추가
# SECRET_KEY=your-secret-key
# OPENAI_API_KEY=your-openai-api-key
# MONGODB_URI=mongodb://localhost:27017/
# DATABASE_NAME=tour_expense

# 서버 실행 (포트 5001)
python app.py
```

### Frontend 설정

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행 (포트 3001)
npm start
```

## 📁 프로젝트 구조

```
tour_expense/
├── backend/
│   ├── app.py              # Flask 앱 팩토리
│   ├── config.py           # 설정 (환율, 참가자 등)
│   ├── requirements.txt    # Python 의존성
│   ├── models/
│   │   └── expense.py      # 경비 모델
│   ├── routes/
│   │   └── expense_routes.py  # API 라우트
│   ├── services/
│   │   ├── ocr_service.py  # OCR 분석 서비스
│   │   └── database.py     # MongoDB 연결
│   └── uploads/            # 업로드된 영수증 이미지
│
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.js          # 메인 컴포넌트
│   │   ├── App.css         # 스타일
│   │   └── index.js        # 엔트리 포인트
│   └── package.json
│
└── README.md
```

## 🔧 설정 변경

### 환율 수정
`backend/config.py`에서 기본 환율을 수정하거나, 앱에서 실시간으로 변경 가능:

```python
EXCHANGE_RATES = {
    'KRW': 1.0,
    'JPY': 9.5,      # 1 JPY = 9.5 KRW
    'USD': 1350.0    # 1 USD = 1350 KRW
}
```

### 참가자 수정
`backend/config.py`에서 참가자 명단 수정:

```python
PARTICIPANTS = ['공훈의', '최철기', '이태수', '강경수']
```

### 지출 항목 수정
```python
EXPENSE_CATEGORIES = ['교통비', '식사비', '음료/간식', '숙박비', '기타']
```

## 📝 API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/health` | 서버 상태 확인 |
| GET | `/api/config` | 설정 정보 조회 |
| GET | `/api/expenses` | 모든 경비 조회 |
| POST | `/api/expenses` | 경비 등록 |
| DELETE | `/api/expenses/:id` | 경비 삭제 |
| POST | `/api/upload-receipt` | 영수증 업로드 및 분석 |
| GET | `/api/summary` | 경비 요약 및 분담금 계산 |
| PUT | `/api/exchange-rates` | 환율 업데이트 |

## 🎨 스크린샷

앱은 다크 테마의 모던한 UI를 제공합니다:
- 영수증 드래그 앤 드롭 업로드
- 실시간 OCR 분석 결과 표시
- 경비 내역 테이블
- 카테고리별 지출 차트
- 참가자별 정산 내역

## 📄 라이선스

MIT License
