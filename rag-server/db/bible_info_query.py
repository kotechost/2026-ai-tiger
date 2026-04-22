import json


async def get_next_crawl_no(conn) -> int:
    row = await conn.fetchrow(
        "SELECT COALESCE(MAX(crawl_no), 0) + 1 AS next_no FROM bible_book_info"
    )
    return row["next_no"]


async def save_bible_to_db(pool, data: dict):
    async with pool.acquire() as conn:
        crawl_no = await get_next_crawl_no(conn)
        print(f"[bibleInfo] DB 저장 시작 (crawl_no={crawl_no})", flush=True)

        rows = []
        for version_code, version_data in data.items():
            version_name = version_data["version_name"]
            for book in version_data["books"]:
                raw_json = json.dumps(book, ensure_ascii=False)
                for chapter in book["chapters"]:
                    rows.append((
                        crawl_no,
                        version_code,
                        version_name,
                        book["book_order"],
                        book["name"],
                        book["book"],
                        chapter["chap"],
                        chapter["secs"],
                        book["total_chap"],
                        book["total_sec"],
                        raw_json,
                        "Y",
                    ))

        await conn.executemany(
            """
            INSERT INTO bible_book_info
                (crawl_no, version_code, version_name, book_order, book_name, book_code,
                 chap, chap_sec_cnt, total_chap, total_sec, raw_json, use_yn)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            rows,
        )
        print(f"[bibleInfo] DB 저장 완료 — crawl_no={crawl_no}, {len(rows)}건 삽입", flush=True)
