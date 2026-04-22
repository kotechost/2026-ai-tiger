import json
import httpx
import asyncio  # 큐 및 타임아웃 관리를 위해 추가
from fastapi import FastAPI, UploadFile
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

# RAG 관련 모듈
from rag.search import search_context, match_source
from rag.search_doc import search_document
from rag.crawl_to_vector import crawl_and_store
from rag.document_to_vector import document_to_vector
from rag.pdf_parser import parse_pdf_to_page_items

print("🚀 API Server Loading...", flush=True)

# ⭐ 여러 Ollama 서버 정의
OLLAMA_SERVERS = [
    "http://host.docker.internal:11436/api/chat"
]

# 1️⃣ [추가] 동시 요청 제한을 위한 세마포어 (GPU가 3개이므로 동시 처리 3~4개가 적당)
MAX_CONCURRENT_REQUESTS = 4

# ⭐ 전역 상태 관리 객체
class ServerState:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.index = 0
        self.index_lock = asyncio.Lock()
        self.client = None

state = ServerState()

# 2️⃣ [추가] 라운드 로빈(순차분배)을 위한 인덱스
server_index = 0

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 API Server Loading...", flush=True)
    # HTTP 클라이언트를 하나만 생성하여 재사용 (성능 핵심)
    state.client = httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    )
    print("✅ RAG API Server & HTTP Client Started")
    yield
    await state.client.aclose()
    print("🛑 RAG API Server Stopped")

app = FastAPI(lifespan=lifespan)
app.mount("/pdf", StaticFiles(directory="./pdfs"), name="pdf")

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: list[Message]

@app.get("/v1/models")
async def get_models():
    return {
        "object": "list",
        "data": [{"id": "rag-qwen", "object": "model", "owned_by": "rag-api"}]
    }

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    acquired = False
    try:
        # ✅ state.semaphore 로 수정
        await asyncio.wait_for(state.semaphore.acquire(), timeout=10)
        acquired = True
    except asyncio.TimeoutError:
        async def error_stream():
            yield 'data: {"choices":[{"delta":{"content":"⚠️ 서버가 바쁩니다. 잠시 후 다시 시도해주세요."}}]}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

   
    user_question = req.messages[-1].content

    if any(keyword in user_question.lower() for keyword in ["follow-up", "suggest", "generate a concise", "generate 1-3 broad tags", "chat history"]):
        if acquired:
            state.semaphore.release()
        return {
            "id": "chatcmpl-followup",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]
        }

    async with state.index_lock:
            idx = state.index
            state.index = (state.index + 1) % len(OLLAMA_SERVERS)

    ollama_url = OLLAMA_SERVERS[idx]
    
    # RAG 검색 로직 (기존 유지)
    context_web, web_docs, web_scores, recommendList = "", [], [], []
    context_doc, doc_docs, doc_scores, doc_sources = await asyncio.to_thread(
        search_document, user_question
    )

    is_doc_based = bool(context_doc)
    doc_flag_text = "문서 있음" if is_doc_based else "문서 없음"

    context_text = ""
    if context_web:
        context_text += f"[웹사이트 문서]\n{context_web}"
    if context_doc:
        context_text += f"\n\n[업로드 문서]\n{context_doc}"

    context_text = context_text[:3000]

    # 프롬프트 규칙 (기존 유지)
    prompt_text = f"""너는 순천향대학교 2023년 대학요람 문서를 기반으로 질문에 답하는 AI이다.

[문서 여부]
{doc_flag_text}

[문서]
{context_text}

[질문]
{user_question}

[답변 규칙]
- 문서에 포함된 정보를 기반으로 답하라
- 문서에 명시적으로 적혀있는 정보만 답변하라
- 문서에 없는 내용은 추측하거나 유추하지 마라
- "~일 수 있다", "~로 추정된다", "추가 정보가 필요합니다" 같은 표현을 사용하지 마라
- 조건에 정확히 일치하는 정보만 포함하고, 일치하지 않으면 아예 언급하지 마라
- 예시: "부교수 알려줘"라고 하면 문서에 "부교수"로 명시된 사람만 답하고, "교수"로 적힌 사람은 포함하지 마라

- 문서 내용이 없을 경우:
  - 먼저 일반적인 설명을 간단히 제공한 후
  - 아래 문장을 함께 안내하라

  저는 순천향대학교 2023년 대학요람 문서와 관련된 내용만 정확히 안내해 드릴 수 있어요.
- 불필요하게 딱딱한 표현은 피하고 자연스럽게 설명하라
- 사용자 질문 의도를 파악하여 필요한 만큼만 설명하라

[답변 표시 규칙]
- 문서 기반이면 반드시 맨 위에 "📄 문서 기반 답변입니다" 출력
- 문서 기반이 아니면 "🤖 일반 답변입니다 (참고용)" 출력

[답변 형식 규칙]
- 질문에 맞게 자연스럽게 답변하라
- 항상 정해진 형식을 따르지 말고 상황에 맞게 설명하라
- 필요할 경우 아래 구조를 사용할 수 있다:

[핵심 요약]
- 핵심 내용을 간단히 정리

[상세 설명]
- 문단 형태로 설명

[추가 정보]
- bullet point(-) 사용 가능

- 번호(1,2,3)는 필요할 때만 사용하라
- 과도하게 구조화하지 말고 자연스럽게 설명하라

[중요]
- 문서 기반 정보가 있을 경우 이를 우선하여 답변하라
- 문서 기반 여부를 반드시 명확히 표시하라

답변:"""

    async def generate_stream():
        response = None
        try:
            async with state.client.stream(
                "POST",
                ollama_url,
                json={
                    "model": "qwen2:7b",
                    "messages": [{"role": "user", "content": prompt_text}],
                    "stream": True,
                    "keep_alive": 120,
                    "options": {
                        "temperature": 0.1,
                        "top_k": 3,
                        "num_ctx": 4096,
                        "num_thread": 4
                    }
                }
            ) as response:
                if response.status_code != 200:
                    raise Exception(f"Ollama error: {response.status_code}")
                start_time = asyncio.get_event_loop().time()
                first_chunk_received = False
                last_chunk_time = start_time

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    now = asyncio.get_event_loop().time()

                    # 🔥 중간 멈춤 감지
                    if now - last_chunk_time > 15:
                        raise TimeoutError("응답 중간 멈춤")

                    last_chunk_time = now

                    # 🔥 첫 응답 timeout
                    if not first_chunk_received:
                        if now - start_time > 12:
                            raise TimeoutError("첫 응답 지연")
                        first_chunk_received = True

                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue
                    content = chunk.get("message", {}).get("content", "")

                    if content:
                        data = {
                            "id": "chatcmpl-rag",
                            "object": "chat.completion.chunk",
                            "choices": [{
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(data)}\n\n"

                    if chunk.get("done"):
                        if doc_sources:
                            yield f'data: {json.dumps({"sources": doc_sources})}\n\n'

                        yield "data: [DONE]\n\n"

        except Exception as err:
            print(f"❌ Streaming Error: {err}", flush=True)
            try:
                if response and not response.is_closed:
                    await response.aclose()
            except:
                pass
            yield f'data: {json.dumps({"choices":[{"delta":{"content":"⚠️ 서버 지연 발생"}}]})}\n\n'
            yield "data: [DONE]\n\n"

        finally:
            if acquired:
                state.semaphore.release()
    return StreamingResponse(generate_stream(), media_type="text/event-stream")

@app.post("/v1/documents")
async def upload_document(file: UploadFile, parser_name: str = "fitz"):

    print("===== 문서 업로드 시작 =====", flush=True)

    content = await file.read()
    fileNameStr = file.filename or "unknown"

    pageItemList = []

    if fileNameStr.lower().endswith(".pdf"):

        pageItemList = parse_pdf_to_page_items(content, parser_name=parser_name)

    else:

        try:
            textStr = content.decode("utf-8")
        except:
            textStr = content.decode("latin-1")

        textStr = textStr.strip()

        if textStr:
            pageItemList.append({
                "page": None,
                "text": textStr
            })

    if not pageItemList:
        return {
            "status": "error",
            "filename": fileNameStr,
            "message": "텍스트를 추출하지 못했습니다."
        }

    document_to_vector(pageItemList, fileNameStr)

    print("===== 문서 업로드 완료 =====", flush=True)

    return {
        "status": "ok",
        "filename": fileNameStr,
        "pages": len(pageItemList)
    }