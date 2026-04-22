import re
import asyncio
from fastapi import APIRouter
from bs4 import BeautifulSoup
from state import state
from db.bible_crawl_query import get_next_crawl_group_no, get_crawl_targets, upsert_crawl_content
from db.config.database import init_db_pool, close_db_pool

BIBLE_LIST_JS_URL = "https://www.bskorea.or.kr/bible/js/bible.list.js"
BIBLE_VERSIONS    = {"GAE": "개역개정", "SAENEW": "새번역"}

router = APIRouter(tags=["Bible"])

BIBLE_CONTENT_URL = "https://www.bskorea.or.kr/bible/korbibReadpage.php"


async def _fetch_chapter_html(version: str, book: str, chap: int):
    """성경 장 페이지 HTML 크롤링 (사이트 부하 최소화: 1초 대기)"""
    url = f"{BIBLE_CONTENT_URL}?version={version}&book={book}&chap={chap}&sec=1"
    try:
        r = await state.client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        await asyncio.sleep(1.0)
        return r.text, url
    except Exception as e:
        await asyncio.sleep(2.0)
        raise e


def _parse_chapter_html(html: str) -> dict:
    """
    HTML에서 대표 제목 · 소제목 · 절 번호 · 본문 텍스트 파싱

    파싱 대상 구조 예시:
      <div class="titleBg">[창세기 1:1   ]</div>
      <div id="tdBible1">
        <font class="smallTitle">천지 창조</font>
        <span ...><span class="number">1&nbsp;&nbsp;&nbsp;</span>태초에...</span>
        <span ...><span class="number">2&nbsp;&nbsp;&nbsp;</span>땅이...</span>
      </div>
    """
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    title_div = soup.find("div", class_="titleBg")
    if title_div:
        title = re.sub(r'\s+', '', title_div.get_text())

    bible_div = soup.find("div", id="tdBible1")
    verses = []

    if bible_div:
        current_small_title = None
        seen_secs = set()

        # descendants: <H VAL=1.1> 같은 비정상 태그가 닫히지 않아
        # 절 span들이 그 안에 갇히는 경우를 포함해 전체 탐색.
        for elem in bible_div.descendants:
            if not hasattr(elem, 'name') or elem.name is None:
                continue

            # 소제목 추적
            if elem.name == "font" and "smallTitle" in (elem.get("class") or []):
                current_small_title = elem.get_text(strip=True)
                continue

            # 절 번호 span 탐지 → 부모 span에서 본문 추출
            if elem.name == "span" and "number" in (elem.get("class") or []):
                # "1-3   " → [1,2,3] / "12-13   " → [12,13] / "5   " → [5]
                _nums = re.findall(r'\d+', elem.get_text())
                if len(_nums) == 2:
                    sec_nums = list(range(int(_nums[0]), int(_nums[1]) + 1))
                elif len(_nums) == 1:
                    sec_nums = [int(_nums[0])]
                else:
                    sec_nums = []
                if not sec_nums or sec_nums[0] in seen_secs:
                    continue
                seen_secs.update(sec_nums)

                parent_span = elem.parent
                if parent_span:
                    # D2 팝업 각주 텍스트 수집 후 제거
                    d2_texts = []
                    for hidden in parent_span.find_all("div", class_="D2"):
                        t = hidden.get_text(strip=True)
                        if t:
                            d2_texts.append(t)
                        hidden.decompose()
                    full_text = parent_span.get_text()
                else:
                    d2_texts = []
                    full_text = elem.get_text()
                d2_hide_content = "\n\n".join(d2_texts) if d2_texts else None
                verse_text = re.sub(r'^\d+(?:-\d+)?\s*', '', full_text).strip()
                for sec in sec_nums:
                    verses.append({
                        "sec":            sec,
                        "verse_text":     verse_text,
                        "d2_hide_content": d2_hide_content,
                        "small_title": current_small_title,
                    })

    return {"title": title, "verses": verses}


async def _run_bible_crawl():
    """
    bible_book_info 테이블 기준으로 성경 본문 크롤링 후 bible_crawl_content 에 저장.
    - use_yn = 'Y' 이고 crawl_no 가 최신인 레코드 기준
    - version_code / book_code / chap 단위로 페이지 요청
    - 절 단위 UPSERT (uk_bible_crawl_content_01: version_code, book_code, chap, sec)
    """
    if not state.db_pool:
        print("[bibleCrawl] ⚠️  DB 풀 없음 — 크롤링 중단", flush=True)
        state.crawl_running = False
        return

    try:
        async with state.db_pool.acquire() as conn:
            crawl_group_no = await get_next_crawl_group_no(conn)
            targets = await get_crawl_targets(conn)

        total = len(targets)
        print(f"[bibleCrawl] 크롤링 시작 — crawl_group_no={crawl_group_no}, 대상={total}건", flush=True)

        for i, row in enumerate(targets, 1):
            version_code = row["version_code"]
            version_name = row["version_name"]
            book_code    = row["book_code"]
            book_name    = row["book_name"]
            book_order   = row["book_order"]
            chap         = row["chap"]

            try:
                html, source_url = await _fetch_chapter_html(version_code, book_code, chap)
                parsed = _parse_chapter_html(html)

                if not parsed["verses"]:
                    print(f"[bibleCrawl] [{i}/{total}] {version_code} {book_name} {chap}장 — 절 파싱 결과 없음", flush=True)
                    continue

                upsert_rows = [
                    (
                        crawl_group_no,
                        book_order,
                        version_code,
                        version_name,
                        book_code,
                        book_name,
                        chap,
                        v["sec"],
                        re.sub(r':\d+\]', f':{v["sec"]}]', parsed["title"]),
                        v["small_title"],
                        v["verse_text"],
                        re.sub(r'sec=\d+', f'sec={v["sec"]}', source_url),
                        "Y",
                        v.get("d2_hide_content"),
                    )
                    for v in parsed["verses"]
                ]

                async with state.db_pool.acquire() as conn:
                    await upsert_crawl_content(conn, upsert_rows)

                print(
                    f"[bibleCrawl] [{i}/{total}] {version_code} {book_name} {chap}장"
                    f" — {len(parsed['verses'])}절 저장 완료",
                    flush=True,
                )

            except Exception as e:
                print(f"[bibleCrawl] [{i}/{total}] {version_code} {book_name} {chap}장 — 오류: {e}", flush=True)

        print(f"[bibleCrawl] 크롤링 완료 — crawl_group_no={crawl_group_no}, 총 {total}건 처리", flush=True)

    except Exception as e:
        print(f"[bibleCrawl] 크롤링 실패: {e}", flush=True)

    finally:
        state.crawl_running = False
        await close_db_pool()


@router.post(
    "/v1/bibleCrawl",
    summary="수집테이블(bible_crawl_content) 기반 성경 본문 크롤링 시작",
    description="""
대한성서공회 사이트에서 성경 본문(절 단위)을 크롤링하여 `bible_crawl_content` 테이블에 저장합니다.

**크롤링 기준**
- `bible_book_info` 테이블에서 `use_yn='Y'`이고 `crawl_no`가 최신인 레코드를 조회
- `version_code` / `book_code` / `chap` 단위로 아래 URL 순차 호출

**동작 방식**
- 크롤링은 **백그라운드**에서 실행되며 API는 즉시 응답합니다.
- 사이트 부하 방지를 위해 페이지 요청 간 **1초** 대기합니다.
- 이미 저장된 절은 **UPSERT** (덮어쓰기) 처리됩니다.
- 동시에 두 번 이상 실행되지 않습니다 (`already_running` 응답).
""",
)
async def bible_crawl():
    if state.crawl_running:
        return {
            "status":  "already_running",
            "message": "이미 크롤링이 진행 중입니다. 서버 로그에서 진행 상황을 확인하세요.",
        }

    if not state.db_pool:
        await init_db_pool()

    state.crawl_running = True
    asyncio.create_task(_run_bible_crawl())

    return {
        "status":  "started",
        "message": "크롤링이 백그라운드에서 시작되었습니다. 서버 로그에서 진행 상황을 확인하세요.",
    }


# ─── bibleCrawlFromJs : bible.list.js 직접 파싱 → 크롤링 ──────────────────────

def _parse_book_list_from_js(js: str, version: str) -> list[dict]:
    """
    bible.list.js 에서 szGAEBook / szSAENEWBook 배열을 파싱하여 책 목록 반환.

    예) szGAEBook[0] = new Array("창세기","gen","1","2",...,"50");
      → {"book_order":1, "book_name":"창세기", "book_code":"gen", "total_chap":50}
    """
    pattern = rf'sz{version}Book\[(\d+)\]\s*=\s*new Array\(([^)]+)\)'
    books = []
    for idx, args in re.findall(pattern, js):
        parts = [p.strip().strip('"') for p in args.split(',')]
        books.append({
            "book_order": int(idx) + 1,
            "book_name":  parts[0],
            "book_code":  parts[1],
            "total_chap": len(parts) - 2,
        })
    return books


async def _run_bible_crawl_from_js():
    """
    bible.list.js 에서 GAE·SAENEW 책 목록을 직접 파싱하여
    bible_book_info 테이블 없이 bible_crawl_content 에 바로 저장.
    """
    if not state.db_pool:
        print("[bibleCrawlFromJs] ⚠️  DB 풀 없음 — 크롤링 중단", flush=True)
        state.crawl_js_running = False
        return

    try:
        # 1) bible.list.js 에서 책 목록 수집
        r = await state.client.get(BIBLE_LIST_JS_URL, headers={"User-Agent": "Mozilla/5.0"})
        js = r.text

        # 2) crawl_group_no 채번
        async with state.db_pool.acquire() as conn:
            crawl_group_no = await get_next_crawl_group_no(conn)

        # 3) 버전별 순회
        for version_code, version_name in BIBLE_VERSIONS.items():
            books = _parse_book_list_from_js(js, version_code)
            total_books = len(books)
            print(
                f"[bibleCrawlFromJs] {version_name}({version_code}) — {total_books}권 파싱 완료"
                f" (crawl_group_no={crawl_group_no})",
                flush=True,
            )

            for b in books:
                book_order = b["book_order"]
                book_name  = b["book_name"]
                book_code  = b["book_code"]
                total_chap = b["total_chap"]

                for chap in range(1, total_chap + 1):
                    try:
                        html, source_url = await _fetch_chapter_html(version_code, book_code, chap)
                        parsed = _parse_chapter_html(html)

                        if not parsed["verses"]:
                            print(
                                f"[bibleCrawlFromJs] {version_code} {book_name} {chap}장"
                                f" — 절 파싱 결과 없음",
                                flush=True,
                            )
                            continue

                        upsert_rows = [
                            (
                                crawl_group_no,
                                book_order,
                                version_code,
                                version_name,
                                book_code,
                                book_name,
                                chap,
                                v["sec"],
                                re.sub(r':\d+\]', f':{v["sec"]}]', parsed["title"]),
                                v["small_title"],
                                v["verse_text"],
                                re.sub(r'sec=\d+', f'sec={v["sec"]}', source_url),
                                "Y",
                            )
                            for v in parsed["verses"]
                        ]

                        async with state.db_pool.acquire() as conn:
                            await upsert_crawl_content(conn, upsert_rows)

                        print(
                            f"[bibleCrawlFromJs] {version_code} {book_name} {chap}/{total_chap}장"
                            f" — {len(parsed['verses'])}절 저장 완료",
                            flush=True,
                        )

                    except Exception as e:
                        print(
                            f"[bibleCrawlFromJs] {version_code} {book_name} {chap}장 — 오류: {e}",
                            flush=True,
                        )

        print(
            f"[bibleCrawlFromJs] 전체 크롤링 완료 — crawl_group_no={crawl_group_no}",
            flush=True,
        )

    except Exception as e:
        print(f"[bibleCrawlFromJs] 크롤링 실패: {e}", flush=True)

    finally:
        state.crawl_js_running = False
        await close_db_pool()


@router.post(
    "/v1/bibleCrawlFromJs",
    summary="성경 본문 크롤링 (bible.list.js 직접 참조 - 개역개정/새번역 전체 크롤링)",
    description="""
`bible.list.js` 에서 **개역개정(GAE)** · **새번역(SAENEW)** 책 목록을 직접 파싱하여
`bible_book_info` 테이블 없이 바로 본문 크롤링을 수행합니다.

**크롤링 기준**
- `https://www.bskorea.or.kr/bible/js/bible.list.js` 의 `szGAEBook` / `szSAENEWBook` 배열 파싱
- 배열 구조: `new Array("책이름", "book코드", "1", "2", ..., "N장")`
- `version_code` / `book_code` / `chap` 단위로 아래 URL 순차 호출
  ```
  https://www.bskorea.or.kr/bible/korbibReadpage.php?version={version}&book={book}&chap={chap}&sec=1
  ```

**동작 방식**
- 크롤링은 **백그라운드**에서 실행되며 API는 즉시 응답합니다.
- 사이트 부하 방지를 위해 페이지 요청 간 **1초** 대기합니다.
- 이미 저장된 절은 **UPSERT** 처리됩니다.
- 동시에 두 번 이상 실행되지 않습니다 (`already_running` 응답).
""",
    tags=["Bible"],
)
async def bible_crawl_from_js():
    if state.crawl_js_running:
        return {
            "status":  "already_running",
            "message": "이미 JS 기반 크롤링이 진행 중입니다. 서버 로그에서 진행 상황을 확인하세요.",
        }

    if not state.db_pool:
        await init_db_pool()

    state.crawl_js_running = True
    asyncio.create_task(_run_bible_crawl_from_js())

    return {
        "status":  "started",
        "message": "JS 기반 크롤링이 백그라운드에서 시작되었습니다. 서버 로그에서 진행 상황을 확인하세요.",
    }
