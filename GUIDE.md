# FastAPI 프로젝트 가이드

## 프로젝트 구조
```
fastapi/
├── main.py           # 메인 FastAPI 애플리케이션
├── requirements.txt  # 의존성 패키지 목록
├── .gitignore       # Git 무시 파일 목록
├── app/             # 앱 모듈 디렉토리
├── static/          # 정적 파일 (HTML, CSS, JS)
└── GUIDE.md         # 이 가이드 파일
```

## 설치 및 실행 방법

### 1. Python 3.11+ 설치 (필수)
llama-scan을 사용하기 위해 Python 3.11 이상이 필요합니다.

#### macOS (Homebrew 사용):
```bash
brew install python@3.11
```

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv
```

#### Windows:
Python.org에서 Python 3.11+ 설치

### 2. 가상환경 생성 및 활성화
```bash
# 기존 가상환경이 있다면 삭제
rm -rf venv

# Python 3.11로 새 가상환경 생성 (macOS/Linux)
python3.11 -m venv venv
# 또는 Python 3.11이 기본인 경우
python3 -m venv venv

# 가상환경 활성화 (macOS/Linux)
source venv/bin/activate

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# Python 버전 확인 (3.11+여야 함)
python --version
```

### 3. 패키지 설치
```bash
# pip 업그레이드
pip install --upgrade pip

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 4. Vision 모델 설치 (llama-scan용)
```bash
# 기본 Vision 모델 설치
ollama pull qwen2.5vl:latest

# 또는 더 작은 모델 (선택사항)
ollama pull qwen2.5vl:3b
```

### 5. 서버 실행
```bash
# 개발 모드 (파일 변경 시 자동 재시작)
uvicorn main:app --reload

# 또는 특정 호스트/포트 지정
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 또는 Python으로 직접 실행
python main.py
```

## API 접근 주소

- **API 서버**: http://localhost:8000
- **자동 API 문서 (Swagger)**: http://localhost:8000/docs
- **ReDoc 문서**: http://localhost:8000/redoc
- **아이템 테스트 페이지**: http://localhost:8000/test
- **PDF 분석 테스트 페이지**: http://localhost:8000/pdf-test

## API 엔드포인트

### 기본 엔드포인트
- `GET /` - Hello World 메시지

### PDF 분석 API (메인 기능)
- `GET /ollama/models` - 사용 가능한 Ollama 모델 목록 조회
- `POST /pdf/analyze` - PDF 파일 업로드 및 AI 분석
- `GET /pdf-test` - PDF 분석 테스트 웹 인터페이스

### PDF 분석 요청 형식
```bash
curl -X POST "http://localhost:8000/pdf/analyze" \
  -F "file=@document.pdf" \
  -F "scan_model=qwen2.5vl:latest" \
  -F "analysis_model=gemma3:4b" \
  -F "custom_prompt=이 문서의 핵심 내용을 요약해주세요"
```

### PDF 분석 응답 형식
```json
{
  "filename": "document.pdf",
  "text_content": "추출된 텍스트 내용...",
  "analysis": "AI 분석 결과...",
  "scan_model_used": "qwen2.5vl:latest",
  "analysis_model_used": "gemma3:4b",
  "page_count": 5
}
```

### 아이템 관리 API (예제용)
- `GET /items` - 모든 아이템 조회
- `GET /items/{item_id}` - 특정 아이템 조회
- `POST /items` - 새 아이템 생성
- `PUT /items/{item_id}` - 아이템 수정
- `DELETE /items/{item_id}` - 아이템 삭제

## 테스트 방법

### 1. PDF 분석 테스트 (메인 기능)
- **웹 인터페이스**: http://localhost:8000/pdf-test
- PDF 파일 업로드하고 즉시 분석 결과 확인
- 이미지/다이어그램 포함된 복잡한 PDF도 완벽 분석

### 2. Swagger UI 사용
- http://localhost:8000/docs 접속
- 각 API 엔드포인트를 직접 테스트 가능

### 3. 커스텀 테스트 페이지 사용
- **아이템 API**: http://localhost:8000/test
- **PDF 분석**: http://localhost:8000/pdf-test

### 4. curl 명령어 예제

#### PDF 분석:
```bash
# PDF 파일 분석
curl -X POST "http://localhost:8000/pdf/analyze" \
  -F "file=@your_document.pdf" \
  -F "scan_model=qwen2.5vl:latest" \
  -F "analysis_model=gemma3:4b"

# 사용 가능한 모델 조회
curl http://localhost:8000/ollama/models
```

#### 아이템 API (예제):
```bash
# 모든 아이템 조회
curl http://localhost:8000/items

# 새 아이템 생성
curl -X POST "http://localhost:8000/items" \
     -H "Content-Type: application/json" \
     -d '{"name":"테스트 아이템","description":"테스트용","price":99.99}'
```

## 개발 팁

### FastAPI vs Next.js 비교
- **라우팅**: Next.js의 파일 기반 라우팅 vs FastAPI의 데코레이터 기반 라우팅
- **타입 안정성**: TypeScript vs Python의 타입 힌트
- **자동 문서화**: FastAPI는 자동으로 OpenAPI 문서 생성
- **데이터 검증**: Pydantic 모델 vs Zod 등의 라이브러리

### 주요 기술 스택 (완전 로컬 환경)
1. **FastAPI**: Python 웹 프레임워크
2. **llama-scan**: 멀티모달 PDF 파싱 (이미지/다이어그램 인식)
3. **Ollama**: 로컬 AI 모델 실행
4. **Pydantic**: 데이터 검증 및 직렬화

### 완전 온프레미스 환경
- **외부 API 불필요**: 모든 처리가 로컬에서 진행
- **인터넷 연결 불필요**: 오프라인 환경에서도 작동
- **인증/인가 없음**: 단순한 API 구조
- **llama-scan**: 이미지와 다이어그램까지 텍스트로 변환
- **멀티모달**: Vision 모델로 복잡한 문서 구조 이해

### llama-scan 특징
- **멀티모달 분석**: 이미지, 다이어그램, 표를 텍스트로 변환
- **Vision 모델 활용**: qwen2.5vl 등 최신 Vision 모델 사용
- **완전 로컬**: 외부 API 호출 없이 온프레미스에서 실행
- **높은 정확도**: 기존 PDF 파서 대비 훨씬 정확한 텍스트 추출

### 사용 가능한 Vision 모델
```bash
# 기본 모델 (권장)
ollama pull qwen2.5vl:latest

# 더 작은 모델
ollama pull qwen2.5vl:3b

# 다른 Vision 모델들
ollama pull llava:latest
ollama pull bakllava:latest
```

### 현재 설치된 상태 ✅
- ✅ Python 3.11.13 설치됨
- ✅ llama-scan 패키지 설치됨  
- ✅ qwen2.5vl:latest 모델 설치됨
- ✅ 서버가 http://localhost:8000 에서 실행 중
- ✅ 바로 테스트 가능한 상태

## 다음 단계
1. 데이터베이스 연동 (SQLAlchemy + PostgreSQL/MySQL)
2. 인증/인가 시스템 구현
3. 테스트 코드 작성 (pytest)
4. Docker를 이용한 컨테이너화
5. 배포 (AWS, Heroku, DigitalOcean 등)