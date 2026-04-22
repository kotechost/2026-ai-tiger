import re
import os
import asyncio
from fastapi import APIRouter
from state import state
from db.bible_info_query import save_bible_to_db
from db.config.database import init_db_pool, close_db_pool

router = APIRouter(tags=["Bible"])

BIBLE_LIST_JS_URL  = "https://www.bskorea.or.kr/bible/js/bible.list.js"
BIBLE_SEC_AJAX_URL = "https://www.bskorea.or.kr/bible/getsec.ajax.php"
BIBLE_VERSIONS     = {"GAE": "개역개정", "SAENEW": "새번역"}

BIBLE_DEBUG       = os.getenv("BIBLE_DEBUG", "0") == "1"
BIBLE_DEBUG_LIMIT = int(os.getenv("BIBLE_DEBUG_LIMIT", "10"))


def _parse_book_list(js: str, version: str) -> list[dict]:
    """bible.list.js 에서 szGAEBook / szSAENEWBook 파싱"""
    pattern = rf'sz{version}Book\[(\d+)\]\s*=\s*new Array\(([^)]+)\)'
    books = []
    for idx, args in re.findall(pattern, js):
        parts = [p.strip().strip('"') for p in args.split(',')]
        books.append({
            "book_order": int(idx) + 1,
            "name":       parts[0],
            "book":       parts[1],
            "total_chap": len(parts) - 2,
        })
    return books


async def _fetch_verse_count(version: str, book: str, chap: int) -> int:
    """getsec.ajax.php 로 해당 장의 총 절 수 반환 (순차 호출용)"""
    url = f"{BIBLE_SEC_AJAX_URL}?version={version}&book={book}&chap={chap}&sec=1"
    try:
        r = await state.client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        nums = re.findall(r"value='(\d+)'", r.text)
        await asyncio.sleep(1.0)
        return max(int(n) for n in nums) if nums else 0
    except Exception:
        await asyncio.sleep(2.0)
        return 0


async def _build_bible_data() -> dict:
    r = await state.client.get(BIBLE_LIST_JS_URL, headers={"User-Agent": "Mozilla/5.0"})
    js = r.text
    result = {}

    for version, label in BIBLE_VERSIONS.items():
        books = _parse_book_list(js, version)

        if BIBLE_DEBUG:
            books = books[:BIBLE_DEBUG_LIMIT]
            print(f"[bibleInfo] ⚠️  DEBUG 모드: {version} 상위 {BIBLE_DEBUG_LIMIT}권만 수집", flush=True)

        for b in books:
            chapters = []
            for chap in range(1, b["total_chap"] + 1):
                secs = await _fetch_verse_count(version, b["book"], chap)
                chapters.append({"chap": chap, "secs": secs})
            b["chapters"] = chapters
            b["total_sec"] = sum(c["secs"] for c in chapters)
            print(f"[bibleInfo] {version} {b['name']} ({b['book']}): {b['total_chap']}장 {b['total_sec']}절", flush=True)

        result[version] = {"version_name": label, "books": books}

    return result


@router.get(
    "/v1/bibleInfo",
    summary="성경 책 목록 및 장/절 정보 수집",
    description=(
        "개역개정(GAE)·새번역(SAENEW) 두 역본의 책 이름, book 코드, 총 장 수, 총 절 수를 반환합니다.\n\n"
        "첫 호출 시 외부 사이트에서 데이터를 수집하고 DB에 저장하므로 시간이 소요됩니다. "
        "이후 호출은 캐시를 반환하므로 즉시 응답합니다.\n\n"
        "환경변수 `BIBLE_DEBUG=1` 설정 시 상위 10권만 수집합니다."
    ),
)
async def bible_info():
    if state.bible_cache:
        return state.bible_cache

    async with state.bible_lock:
        if state.bible_cache:
            return state.bible_cache

        print("[bibleInfo] 데이터 수집 시작...", flush=True)
        data = await _build_bible_data()
        print("[bibleInfo] 데이터 수집 완료", flush=True)

        if not state.db_pool:
            await init_db_pool()
        await save_bible_to_db(state.db_pool, data)
        await close_db_pool()

        state.bible_cache = data
        print("[bibleInfo] 캐시 저장 완료", flush=True)

    return state.bible_cache
