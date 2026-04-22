# api/bible_vector_stitle.py
import asyncio
import json
import os

from fastapi import APIRouter
from state import state
from db.bible_vector_query import fetch_db_for_vectorize_stitle
from rag.embedding import get_embeddings_batch
from rag.vector_db_stitle import add_vectors_batch, save_index, reset_index  # 소제목 단위 전용 VectorDB
from db.config.database import init_db_pool, close_db_pool

router = APIRouter(tags=["Vector"])
VECTOR_LOG_FILE = "/data/vector_log_stitle.json"      # 소제목 단위 로그 파일
VECTOR_DUMP_FILE = "/data/vectorize_dump_stitle.json"  # 소제목 단위 덤프 파일

async def _run_db_to_vector():
    if not state.db_pool:
        await init_db_pool()

    async with state.db_pool.acquire() as conn:
        rows = await fetch_db_for_vectorize_stitle(conn)

    print(f"[stitlVector] 벡터화 대상: {len(rows)}건", flush=True)

    if not rows:
        return

    reset_index()  # 기존 vector 파일 삭제

    if os.path.exists(VECTOR_LOG_FILE):
        os.remove(VECTOR_LOG_FILE)
        print("[stitlVector] vector_log_stitle.json 삭제 완료", flush=True)

    # 1. 텍스트 수집 — DB에서 소제목 단위로 조회된 rows 처리
    textList = []
    docDictList = []

    for i, row in enumerate(rows):
        version     = row['version_name']
        book        = row['book_name']
        small_title = row['small_title'] or ""
        verse_text  = row['verse_text']  or ""
        url         = row['source_url']  or ""

        title      = f"[{version} {book} {small_title}]"
        text       = f"{title}\n{small_title}\n{verse_text}".strip()
        embed_text = f"소제목: {small_title}\n내용:\n{verse_text}"

        textList.append(embed_text)
        docDictList.append({
            "text":        text,
            "url":         url,
            "title":       title,
            "small_title": small_title,
            "verse_text":  verse_text
        })

        if (i + 1) % 1000 == 0:
            print(f"[stitlVector] 텍스트 수집 중: {i+1}/{len(rows)}건", flush=True)

    print(f"[stitlVector] 소제목 단위 수집 완료: {len(docDictList)}건", flush=True)

    # 2. 배치 임베딩
    print(f"[stitlVector] 배치 임베딩 시작: {len(textList)}건 (소제목 단위)", flush=True)
    vectors = get_embeddings_batch(textList, "passage")

    # textList + vector 매핑 JSON 저장
    dumpEntries = []
    for i, (text, vec) in enumerate(zip(textList, vectors)):
        dumpEntries.append({
            "index":  i,
            "text":   text,
            # "vector": vec.tolist()
        })

    with open(VECTOR_DUMP_FILE, "w", encoding="utf-8") as f:
        json.dump(dumpEntries, f, ensure_ascii=False, indent=2)

    print(f"[stitlVector] text-vector dump 저장: {len(dumpEntries)}건 → {VECTOR_DUMP_FILE}", flush=True)


    # 3. 배치 저장
    add_vectors_batch(vectors, docDictList)

    # JSON 로그 한번에 저장
    logEntries = []
    for docDict in docDictList:
        logEntries.append({
            "소제목": docDict['small_title'],
            "내용":   docDict['verse_text'],
        })

    with open(VECTOR_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logEntries, f, ensure_ascii=False, indent=2)

    print(f"[stitlVector] JSON 로그 저장: {len(logEntries)}건", flush=True)

    save_index()
    print("[stitlVector] VectorDB 저장 완료", flush=True)

    # 벡터화 완료 후 DB 연결 닫기
    await close_db_pool()
    print("[stitlVector] DB 연결 종료", flush=True)


@router.post("/v1/sync-db-stitle",
    summary="DB → VectorDB 동기화 (소제목 단위)",
    description="""
대한성서공회 사이트에서 크롤링한 `bible_crawl_content` 테이블 데이터를 소제목 단위로 VectorDB화.
기존 VectorDB 데이터가 있을경우 삭제하고 재생성합니다.

**VectorDB 기준**
- `bible_crawl_content` 테이블에서 vector_stts_cd = 'READY', use_yn = 'Y' 가 최신인 레코드를 조회
- (version_name, book_name, small_title) 기준으로 그룹핑하여 소제목 단위 벡터 생성

""",
)
async def sync_db_stitle():
    asyncio.create_task(_run_db_to_vector())
    return {"status": "started"}
