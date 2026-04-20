# Local 실행 방법

## 1. Backend

```bash
cd backend
python3 -m venv ../VENV
source ../VENV/bin/activate
pip install -r requirements.txt
python app.py
```

> http://localhost:5001 에서 실행됩니다.

## 2. Frontend (새 터미널)

```bash
cd frontend
npm install
npm start
```

> http://localhost:3001 에서 실행됩니다.

## 3. 필수 환경변수 (`backend/.env`)

```
MONGODB_URI=mongodb://localhost:27017/
GOOGLE_API_KEY=<your-google-api-key>
```
