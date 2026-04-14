# ai_tiger 🐯
문서 · 크롤링 · 교정용 RAG 기반 LLM 시스템

---

## 📌 개요

### 목적
* 문서 수집(크롤링) → 분석 → 교정 → 검색/질의응답까지 통합 처리하는 RAG 기반 LLM 시스템 구축

### 주요 기능
* 문서 처리
* 크롤링
* 교정
* RAG 질의응답
 
---

## 🧱 구성
* RAG API: FastAPI (/v1/bibleInfo, /v1/bibleCrawl, /v1/bibleCrawlFromJs)
* LLM: Qwen (qwen2.5:7b) / EXAONE-4.0-32B (환경변수로 선택)
* Vector DB: FAISS
* DB: PostgreSQL (bible_service)
* UI: OpenWebUI

---

## 🛠 기술 스택
* Backend: FastAPI (Python)
* AI: vLLM / Ollama / Qwen / EXAONE
* DB: PostgreSQL
* Infra: Docker / Docker Compose

---

## 🚀 실행 방법
```bash
docker-compose up -d   # 실행
docker-compose down    # 종료

start.sh               # 빌드 및 재시작
```

---

## 🌐 접속 정보
* UI: http://<서버IP>:3002
* API: http://<서버IP>:8002
* API Docs (Swagger): http://<서버IP>:8002/docs

---

## 📂 디렉토리 구조
```
llm-system-bsk/
├── open-webui/                # Open-WebUI 채팅 UI (SvelteKit + Python 백엔드)
│   ├── backend/               # Python 백엔드 (FastAPI 기반 Open-WebUI 서버)
│   ├── src/                   # SvelteKit 프론트엔드 소스
│   ├── static/                # 정적 파일 (이미지, 폰트, 테마 등)
│   ├── cypress/               # E2E 테스트
│   ├── docs/                  # 문서
│   ├── scripts/               # 빌드/유틸 스크립트
│   ├── test/                  # 단위 테스트
│   └── pdfs/                  # PDF 샘플 파일
│
├── rag-server/                # 커스텀 RAG 서버 (FastAPI)
│   ├── api/                   # API 라우터 (성경 크롤링/정보/벡터 엔드포인트)
│   ├── crawler/               # 웹 크롤러
│   ├── data/                  # 크롤링/처리 데이터
│   ├── db/                    # DB 쿼리 레이어 (PostgreSQL)
│   ├── pdfs/                  # PDF 업로드/처리 디렉터리
│   └── rag/                   # RAG 핵심 로직 (임베딩, 검색, 벡터 DB)
│
├── postgres/                  # PostgreSQL 설정
│   ├── init/                  # DB 초기화 SQL 스크립트
│   └── data/                  # DB 데이터 (볼륨 마운트)
│
└── vector-data/               # 벡터 처리 로그/데이터
```

---

## ⚙️ 환경 변수
```
.env 파일

# PostgreSQL 접속 정보
DB_HOST=host.docker.internal
DB_PORT=5432
DB_NAME=bible
DB_SCHEMA=bible_service
DB_USER=solihost
DB_PASSWORD=soli1234!

# 디버그 모드 (1=ON: 일부 책만 수집, 0=OFF: 전체 수집)
BIBLE_DEBUG=1
BIBLE_DEBUG_LIMIT=2
```

---

## 🤖 모델
```
## qwen2.5:7b

다운로드
ollama pull qwen2.5:7b

ollama 기본 포트 : 11434

## EXAONE-4.0-32B

다운로드
hf download LGAI-EXAONE/EXAONE-4.0-32B-FP8 \
  --local-dir /mnt/hdd22t2/solihost/exaone_models/EXAONE-4.0-32B-FP8 \
  --token hf_your_token_here

vLLM 기본 포트 : 8001

vLLM을 호스트에서 별도 실행 후 사용합니다. 모델 파일은 /mnt/hdd22t2/solihost/exaone_models 에 위치해야 합니다. (위치 변경필요?)


docker-compose.yml의 MODEL_BACKEND 주석을 해제하여 전환합니다.
```

---

## ⚠️ 주의사항
* 포트 충돌 확인
* GPU 사용 여부 설정
* 환경 변수 누락 주의

---

## 👥 팀
* 호혁진
* 정성연
* 이지현
