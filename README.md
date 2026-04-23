# ai_tiger 🐯
문서 · 크롤링 · RAG 기반 LLM 시스템

---

## 📌 개요

### 목적
* 문서 수집(크롤링) → 분석 → 검색/질의응답까지 통합 처리하는 RAG 기반 LLM 시스템 구축

### 주요 기능
* 문서 처리 (PDF 파싱·OCR·청킹·벡터화)
* 크롤링
* RAG 질의응답

---

## 🧱 구성
* RAG API: FastAPI (`/v1/bibleInfo`, `/v1/bibleCrawl`, `/v1/bibleCrawlFromJs`, `/v1/documents` 등)
* LLM: EXAONE-4.5-33B (vLLM 서빙)
* Vector DB: FAISS (성경 / 성경 소제목 / PDF 문서 3종 인덱스)
* Reranker: BAAI/bge-reranker-v2-m3
* DB: PostgreSQL (bible_service)
* UI: OpenWebUI

---

## 🛠 기술 스택
* Backend: FastAPI (Python)
* AI Serving: vLLM
* LLM: EXAONE-4.5-33B
* DB: PostgreSQL
* Infra: Docker / Docker Compose

---

## 🚀 실행 방법
```bash
docker-compose up -d   # 실행
docker-compose down    # 종료

./start.sh             # 빌드 및 재시작
```

> vLLM 서버는 호스트에서 별도 실행합니다. 아래 [vLLM 실행](#-vllm-실행-hostsolihostvllm-package) 섹션 참고.

---

## 🌐 접속 정보
* UI: http://<서버IP>:3002
* API: http://<서버IP>:8002
* API Docs (Swagger): http://<서버IP>:8002/docs
* vLLM API: http://<서버IP>:8005/v1

---

## 📂 디렉토리 구조

<details>
<summary>클릭하여 펼치기</summary>

```
llm-system-bsk/
├── open-webui/                # Open-WebUI 채팅 UI (SvelteKit + Python 백엔드)
│   ├── backend/               # Python 백엔드 (FastAPI 기반 Open-WebUI 서버)
│   ├── src/                   # SvelteKit 프론트엔드 소스
│   ├── static/                # 정적 파일 (이미지, 폰트, 테마 등)
│   ├── cypress/               # E2E 테스트
│   ├── docs/                  # 문서
│   ├── scripts/               # 빌드/유틸 스크립트
│   └── test/                  # 단위 테스트
│
├── rag-server/                # 커스텀 RAG 서버 (FastAPI)
│   ├── api/                   # API 라우터
│   │   ├── bible_info.py            # 성경 정보 조회
│   │   ├── bible_crawl.py           # 성경 크롤링
│   │   ├── bible_vector.py          # 성경 절 단위 벡터화
│   │   ├── bible_vector_stitle.py   # 성경 소제목 단위 벡터화
│   │   └── bible_vector_doc.py      # PDF 문서 업로드 → 벡터화
│   ├── crawler/               # 웹 크롤러
│   ├── db/                    # DB 쿼리 레이어 (PostgreSQL)
│   │   ├── config/                  # DB 연결·풀 설정
│   │   │   ├── connection.py
│   │   │   └── database.py
│   │   ├── init_table/              # 테이블 초기화 스크립트
│   │   ├── bible_crawl_query.py     # 크롤링 성경정보 저장
│   │   ├── bible_info_query.py      # 크롤링 성경정보 대상(Target) 저장
│   │   └── bible_vector_query.py    # 성경 집계 쿼리
│   ├── pdfs/                  # PDF 원본 (정적 마운트 /pdfs)
│   ├── rag/                   # RAG 핵심 로직
│   │   ├── embedding.py             # 임베딩 생성
│   │   ├── chunk.py                 # 텍스트 청킹
│   │   ├── pdf_parser.py            # PDF 파싱 (fitz / VL OCR)
│   │   ├── document_to_vector.py    # PDF 벡터 저장
│   │   ├── vector_db.py             # 성경 FAISS 인덱스
│   │   ├── vector_db_stitle.py      # 성경 소제목 FAISS 인덱스
│   │   ├── vector_db_doc.py         # PDF 문서 FAISS 인덱스
│   │   ├── search.py                # RAG 검색 + rerank + 출처 매칭
│   │   ├── rewrite_query.py         # LLM 기반 질문 재작성
│   │   └── gpu_monitor.py           # GPU 사용률 수집 (날짜별 폴더 저장)
│   ├── main.py                # FastAPI 엔트리포인트
│   ├── state.py               # 전역 상태 (세마포어, httpx 클라이언트, DB 풀)
│   ├── Dockerfile
│   └── requirements.txt
│
├── postgres/                  # PostgreSQL 설정
│   ├── init/                  # DB 초기화 SQL 스크립트
│   └── data/                  # DB 데이터 (볼륨 마운트)
│
├── vllm-package/              # vLLM 실행 패키지 사본 (실 운영본은 /home/solihost/vllm-package)
├── table-data-backup/         # PostgreSQL 테이블 백업 덤프
├── vector-data/               # FAISS 인덱스·덤프 저장 경로
│
├── gpu_log/                   # GPU 사용률 로그 (날짜별, 14일 자동 정리)
│   └── YYYYMMDD/                    # 일자별 폴더
│       └── YYYYMMDD_HHMMSS_fff.log  # 요청 단위 GPU 모니터 로그
├── rag_log/                   # RAG API 컨테이너 stdout 로그 (날짜별, 14일 자동 정리)
│   └── YYYYMMDD/
│       └── YYYYMMDD_HH.log          # 시간 단위 누적 로그
│
├── docker-compose.yml
├── docker-cmd.txt             # 자주 쓰는 docker 커맨드 메모
├── start.sh                   # 빌드·재시작 + 14일 초과 로그 정리
├── log_start.sh               # start.sh 실행 + rag_log 날짜별 tee 저장
└── restart_ui_sh              # OpenWebUI 컨테이너만 재시작
```

</details>

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

# vLLM 연결
VLLM_URL=http://host.docker.internal:8005/v1/chat/completions
VLLM_MODEL_NAME=EXAONE-4.5-33B

# 디버그 모드 (1=ON: 일부 책만 수집, 0=OFF: 전체 수집)
BIBLE_DEBUG=1
BIBLE_DEBUG_LIMIT=2
```

---

## 🤖 모델

### EXAONE-4.5-33B
```bash
# 다운로드
hf download LGAI-EXAONE/EXAONE-4.5-33B \
  --local-dir /home/solihost/exaone_models/EXAONE-4.5-33B \
  --token hf_your_token_here
```

* 서빙: vLLM
* 기본 포트: 8005
* 모델 파일 위치: `/home/solihost/exaone_models/EXAONE-4.5-33B`
* vLLM은 호스트에서 별도 실행 (docker-compose 외부)

---

## 🖥 vLLM 실행 (/home/solihost/vllm-package)

vLLM 구동을 위한 스크립트·가상환경이 `/home/solihost/vllm-package/` 에 분리되어 있습니다.

### 구조
```
/home/solihost/vllm-package/
├── uv-vllm/                # uv 기반 vLLM 가상환경
├── vllm-exaone/            # vLLM 소스 (EXAONE 커스텀 빌드)
├── transformers-exaone/    # transformers 커스텀 (EXAONE 지원)
├── vllm_logs/              # 실행 로그 + latest.log 심볼릭 + vllm.pid
├── vllm_install.sh         # 설치 스크립트
├── run_vllm.sh             # vLLM 서버 백그라운드 실행
├── stop_vllm.sh            # 서버 종료
└── tail_vllm.sh            # 최신 로그 실시간 조회
```

### 실행
```bash
cd /home/solihost/vllm-package
./run_vllm.sh       # nohup 백그라운드 실행, 로그 자동 생성
./tail_vllm.sh      # 최근 로그 tail -f
./stop_vllm.sh      # 서버 종료
```

### 주요 설정 (`run_vllm.sh`)
| 항목 | 값 |
|------|-----|
| Model | `/home/solihost/exaone_models/EXAONE-4.5-33B` |
| Served name | `EXAONE-4.5-33B` |
| Port | `8005` |
| Tensor Parallel | `4` |
| Max model len | `262144` |
| Reasoning parser | `qwen3` |
| Tool call parser | `hermes` (auto tool choice) |
| GPU util | `0.65` |
| Multimodal | `image: 64/prompt` |
| Speculative | MTP (num_speculative_tokens=3) |

---

## ⚠️ 주의사항
* 포트 충돌 확인 (3002 / 8002 / 8005 / 5432)
* GPU 사용 여부 설정 (`run_vllm.sh`의 `--tensor-parallel-size`와 실제 GPU 수 일치)
* vLLM 서버가 먼저 떠 있어야 RAG API가 정상 응답
* 환경 변수 누락 주의

---

## 👥 팀
* 호혁진
* 정성연
* 이지현
