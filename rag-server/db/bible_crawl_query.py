async def get_next_crawl_group_no(conn) -> int:
    row = await conn.fetchrow(
        "SELECT COALESCE(MAX(last_crawl_group_no), 0) + 1 AS next_no"
        " FROM bible_crawl_content"
    )
    return row["next_no"]


async def get_crawl_targets(conn) -> list:
    return await conn.fetch("""
        SELECT version_code, version_name, book_code, book_name, book_order, chap
        FROM bible_book_info
        WHERE use_yn = 'Y'
          AND crawl_no = (SELECT MAX(crawl_no) FROM bible_book_info WHERE use_yn = 'Y')
        ORDER BY version_code, book_order, chap
    """)


async def upsert_crawl_content(conn, rows: list):
    await conn.executemany(
        """
        INSERT INTO bible_crawl_content
            (last_crawl_group_no, last_crawl_page_seq_no,
             version_code, version_name, book_code, book_name,
             chap, sec, title, small_title, verse_text,
             source_url, use_yn, d2_hide_content)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        ON CONFLICT (last_crawl_group_no, version_code, book_code, chap, sec) DO NOTHING
        """,
        rows,
    )
