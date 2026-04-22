async def fetch_db_for_vectorize(conn) -> list:
    return await conn.fetch("""
        SELECT content_id, version_name, book_name, chap, sec,
               title, small_title, verse_text, source_url
        FROM bible_crawl_content
        WHERE vector_stts_cd = 'READY' AND use_yn = 'Y'
        AND last_crawl_group_no = (SELECT MAX(last_crawl_group_no) 
                                    FROM bible_crawl_content
                                )
        ORDER BY content_id asc
    """)

async def fetch_db_for_vectorize_stitle(conn) -> list:
    return await conn.fetch("""
        SELECT version_name, book_name, small_title,
               string_agg(verse_text, E'\n' ORDER BY chap, sec) AS verse_text,
               -- string_agg(chap || '장' || sec || '절 ' || verse_text, E'\n' ORDER BY chap, sec) AS verse_text,
               MIN(source_url) AS source_url
        FROM bible_crawl_content
        WHERE use_yn = 'Y'
          AND last_crawl_group_no = (SELECT MAX(last_crawl_group_no)
                                       FROM bible_crawl_content)
        GROUP BY version_name, last_crawl_page_seq_no, chap, book_name, small_title
        ORDER BY version_name, last_crawl_page_seq_no, chap, MIN(sec)
    """)


async def update_vector_success(conn, content_id: int):
    await conn.execute("""
        UPDATE bible_crawl_content
        SET vector_stts_cd = 'SUCCESS',
            vector_dt = NOW(),
            vector_error_msg = NULL
        WHERE content_id = $1
    """, content_id)

async def update_vector_success_batch(conn, content_ids: list):
    await conn.execute("""
        UPDATE bible_crawl_content
        SET vector_stts_cd = 'SUCCESS',
            vector_dt = NOW(),
            vector_error_msg = NULL
        WHERE content_id = ANY($1)
    """, content_ids)


async def update_vector_fail(conn, content_id: int, error_msg: str):
    await conn.execute("""
        UPDATE bible_crawl_content
        SET vector_stts_cd = 'FAIL',
            vector_error_msg = $1
        WHERE content_id = $2
    """, error_msg, content_id)

async def update_vector_fail_batch(conn, content_ids: list, error_msg: str):
    await conn.execute("""
        UPDATE bible_crawl_content
        SET vector_stts_cd = 'FAIL',
            vector_error_msg = $1
        WHERE content_id = ANY($2)
    """, error_msg, content_ids)

