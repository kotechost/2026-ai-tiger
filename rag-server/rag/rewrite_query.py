from state import state

VAGUE_KEYWORDS = [
    "해당", "그거", "이거", "그것", "이것", "거기", "여기",
    "그 성경", "이 성경", "해당 성경", "그 구절", "이 구절",
    "찾아줘", "알려줘", "더 알려줘", "자세히", "그게 뭐야",
]


async def rewrite_query(question: str, history: str, url: str, model: str) -> str:
    has_vague = any(kw in question for kw in VAGUE_KEYWORDS)
    if not (has_vague and history.strip()):
        return question

    rewrite_prompt = f"""이전 대화를 참고해서 아래 질문을 성경 검색에 적합하게 구체적으로 한 문장으로 재작성해줘. 재작성한 문장만 출력해.

[이전 대화]
{history}

[질문]
{question}

재작성:"""

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": rewrite_prompt}],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 100,
    }
    try:
        resp = await state.client.post(url, json=payload, timeout=10)
        rewritten = resp.json()["choices"][0]["message"]["content"].strip()
        print(f"[쿼리 재작성] {question} → {rewritten}", flush=True)
        return rewritten
    except Exception as e:
        print(f"[쿼리 재작성 실패] {e}", flush=True)
        return question
