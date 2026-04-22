import asyncpg
from state import state
from db.config.connection import DB_HOST, DB_PORT, DB_NAME, DB_SCHEMA, DB_USER, DB_PASSWORD


async def init_db_pool():
    try:
        state.db_pool = await asyncpg.create_pool(
            host=DB_HOST, port=DB_PORT, database=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
            min_size=1, max_size=5,
            server_settings={"search_path": DB_SCHEMA},
        )
        print(f"✅ DB 연결 성공 ({DB_HOST}:{DB_PORT}/{DB_NAME})", flush=True)
    except Exception as e:
        print(f"⚠️  DB 연결 실패: {e}", flush=True)
        state.db_pool = None


async def close_db_pool():
    if state.db_pool:
        await state.db_pool.close()
        state.db_pool = None
