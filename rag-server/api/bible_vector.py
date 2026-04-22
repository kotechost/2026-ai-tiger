# api/bible_vector.py
import asyncio
import json
import os

from fastapi import APIRouter
from state import state
from db.bible_vector_query import fetch_db_for_vectorize, update_vector_success_batch, update_vector_fail_batch
from rag.embedding import get_embeddings_batch
from rag.vector_db import add_vectors_batch, save_index, reset_index
from datetime import datetime
from db.config.database import init_db_pool, close_db_pool

router = APIRouter(tags=["Vector"])
VECTOR_LOG_FILE = "/data/vector_log.json"

# vector + 내용 함께 JSON으로 저장
VECTOR_DUMP_FILE = "/data/vector_dump.json"

async def _run_db_to_vector():
    if not state.db_pool:
        await init_db_pool()

    async with state.db_pool.acquire() as conn:
        rows = await fetch_db_for_vectorize(conn)

    print(f"[dbVector] 벡터화 대상: {len(rows)}건", flush=True)

    if not rows:
        return
    
    reset_index()  # 기존 vector 파일 삭제
    
    if os.path.exists(VECTOR_LOG_FILE):
        os.remove(VECTOR_LOG_FILE)
        print("[dbVector] vector_log.json 삭제 완료", flush=True)

    # 1. 텍스트 수집
    textList = []
    docDictList = []

    for i, row in enumerate(rows):
        title       = f"[{row['version_name']} {row['book_name']} {row['chap']}장 {row['sec']}절]"
        small_title = row['small_title'] or ""
        verse_text  = row['verse_text'] or ""
        url         = row['source_url'] or ""

        text = (
            f"[{row['version_name']} {row['book_name']} "
            f"{row['chap']}장 {row['sec']}절]\n"
            f"{small_title}\n{verse_text}"
        ).strip()

        # embed_text = f"제목: {title}\n내용:\n{text}"
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
            print(f"[dbVector] 텍스트 수집 중: {i+1}/{len(rows)}건", flush=True)

    # 2. 배치 임베딩
    print(f"[dbVector] 배치 임베딩 시작: {len(textList)}건", flush=True)
    vectors = get_embeddings_batch(textList, "passage")

    # textList + vector 매핑 JSON 저장
    VECTOR_DUMP_FILE = "/data/vectorize_dump.json"
    dumpEntries = []
    for i, (text, vec) in enumerate(zip(textList, vectors)):
        dumpEntries.append({
            "index":  i,
            "text":   text,
            # "vector": vec.tolist()
        })

    with open(VECTOR_DUMP_FILE, "w", encoding="utf-8") as f:
        json.dump(dumpEntries, f, ensure_ascii=False, indent=2)

    print(f"[dbVector] text-vector dump 저장: {len(dumpEntries)}건 → {VECTOR_DUMP_FILE}", flush=True)


    # 3. 배치 저장
    add_vectors_batch(vectors, docDictList)

    # JSON 로그 한번에 저장
    logEntries = []
    for row, docDict in zip(rows, docDictList):
        logEntries.append({
            "소제목": docDict['small_title'],
            "내용": docDict['verse_text'],
        })

    with open(VECTOR_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logEntries, f, ensure_ascii=False, indent=2)

    print(f"[dbVector] JSON 로그 저장: {len(logEntries)}건", flush=True)

    save_index()
    print("[dbVector] VectorDB 저장 완료", flush=True)


    # 4. DB 상태 업데이트
    content_ids = [row['content_id'] for row in rows]
    try:
        async with state.db_pool.acquire() as conn:
            await update_vector_success_batch(conn, content_ids)
        print(f"[dbVector] DB 업데이트 완료: {len(content_ids)}건", flush=True)
    except Exception as e:
        print(f"[dbVector] DB 업데이트 실패: {e}", flush=True)
        try:
            async with state.db_pool.acquire() as conn:
                await update_vector_fail_batch(conn, content_ids, str(e))
        except Exception as e2:
            print(f"[dbVector] DB 실패 마킹도 실패: {e2}", flush=True)

    print("[dbVector] DB 벡터화 완료", flush=True)

    # 벡터화 완료 후 DB 연결 닫기
    await close_db_pool()
    print("[dbVector] DB 연결 종료", flush=True)


@router.post("/v1/sync-db", 
    summary="DB → VectorDB 동기화",
    description="""
대한성서공회 사이트에서 크롤링한 `bible_crawl_content` 테이블 데이터를 VectorDB화.
기존 VectorDB 데이터가 있을경우 삭제하고 재생성합니다.

**VectorDB 기준**
- `bible_crawl_content` 테이블에서 vector_stts_cd = 'READY', use_yn = 'Y' 가 최신인 레코드를 조회

""",
)
async def sync_db():
    asyncio.create_task(_run_db_to_vector())
    return {"status": "started"}
