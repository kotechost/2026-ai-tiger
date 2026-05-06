import asyncio

MAX_CONCURRENT_REQUESTS = 24


class ServerState:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.index = 0
        self.index_lock = asyncio.Lock()
        self.client = None
        self.ollama_index = 0
        self.bible_cache = None
        self.bible_lock = None   # lifespan에서 초기화
        self.db_pool = None      # lifespan에서 초기화
        self.crawl_running = False         # bibleCrawl (bible_book_info 기반)
        self.crawl_js_running = False      # bibleCrawlFromJs (bible.list.js 기반)


state = ServerState()
