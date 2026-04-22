import re
import time
import math

from rag.embedding import get_embedding
import rag.vector_db as vdb_bible
import rag.vector_db_stitle as vdb_stitle
import rag.vector_db_doc as vdb_doc
from sentence_transformers import CrossEncoder
from difflib import SequenceMatcher   # 문자열 유사도 비교
from urllib.parse import quote

rerankModel = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cuda")

DEBUG_SEARCH_LOG = True

def get_source_url(docObj):
    """DB 종류에 따라 출처 URL 생성"""
    source_type = docObj.get("source_type", "")

    # 성경: 기존 URL 그대로
    if source_type in ("bible", "bible_stitle"):
        return docObj.get("url", "")

    # PDF: 정적 마운트 경로 + 페이지 앵커
    if source_type == "file":
        file_name = quote(docObj.get("file", ""))
        page_num = docObj.get("page", 0)
        return f"http://localhost:8002/pdfs/{file_name}#page={page_num}"

    return docObj.get("url", "")

def search_context(queryStr):

	print("===== RAG 검색 시작 =====", flush=True)
	print("검색 질문:", queryStr, flush=True)

	# ------------------------------
	# 1️⃣ 질문 벡터 생성 - Query Expansion
	# ------------------------------
	t_embed = time.time()
	queryVec = get_embedding(queryStr, "query")
	print(f"[PERF] embedding: {time.time()-t_embed:.3f}s", flush=True)

	# ------------------------------
	# 2️⃣ FAISS 검색 (후보 40개)
	# ------------------------------
	candidateList = []

	# 3개 DB에서 각각 40개씩 검색
	db_targets = [
		# ("bible",        vdb_bible.indexObj,  vdb_bible.docsList),
		("bible_stitle", vdb_stitle.indexObj, vdb_stitle.docsList),
		("file",         vdb_doc.indexObjDoc, vdb_doc.docsListDoc),
	]

	for db_name, indexObj, docsList in db_targets:
		if indexObj.ntotal == 0:
			print(f"[{db_name}] 인덱스 비어있음 → 스킵", flush=True)
			continue

		distances, indices = indexObj.search(queryVec, 40)
		print(f"[{db_name}] 검색 결과:", indices, flush=True)

		for idxNum, idx in enumerate(indices[0]):
			if idx == -1:
				continue
			if idx < len(docsList):
				doc = docsList[idx]
				if doc is None:
					continue
				docObj = dict(doc)
				docObj["_score"] = float(distances[0][idxNum])
				docObj["_db"]    = db_name
				candidateList.append(docObj)

				print(f"[{db_name}] FAISS 후보 인덱스: {idx}", flush=True)
				print(f"[{db_name}] FAISS 후보[{idxNum}]: {docObj.get('text', '')[:200]}", flush=True)

	# ------------------------------
	# 후보 문서 없는 경우 종료
	# ------------------------------
	if len(candidateList) == 0:
		print("검색 결과 없음", flush=True)
		print("===== RAG 검색 종료 =====", flush=True)
		return "", [], []

	# FAISS 점수 기준 상위 40개로 추림
	candidateList.sort(key=lambda d: d["_score"], reverse=True)
	candidateList = candidateList[:40]

	print("총 FAISS 후보 개수:", len(candidateList), flush=True)


	# =====================================================
	# 4️⃣ 문자열 기반 필터링
	# =====================================================

	# filteredList = []

	# queryClean = queryStr.replace(" ", "")
	# queryWords = queryStr.split()

	# for docObj in candidateList:

	# 	textStr = docObj.get("text", "")
	# 	titleStr = docObj.get("title", "")

	# 	combinedStr = titleStr + " " + textStr
	# 	textClean = combinedStr.replace(" ", "")

	# 	# ------------------------------
	# 	# 1️⃣ 공백 제거 후 전체 문자열 포함 검사
	# 	# ------------------------------
	# 	if queryClean in textClean:
	# 		filteredList.append(docObj)
	# 		continue

	# 	# ------------------------------
	# 	# 2️⃣ 단어 매칭 검사
	# 	# ------------------------------
	# 	if any(word in combinedStr for word in queryWords):
	# 		filteredList.append(docObj)
	# 		continue

	# 	# ------------------------------
	# 	# 3️⃣ 문자열 유사도 검사
	# 	# ------------------------------
	# 	ratioVal = SequenceMatcher(None, queryClean, textClean[:200]).ratio()

	# 	if ratioVal > 0.25:
	# 		filteredList.append(docObj)

	# if len(filteredList) > 0:
	# 	candidateList = filteredList

	# print("필터 후 후보 개수:", len(candidateList), flush=True)


	# ==========================
	# 5️⃣ FAISS 순서 그대로 사용
	# ==========================
	# scoredDocs = [(0.0, doc) for doc in candidateList]

	# print("===== FAISS 순서 결과 =====", flush=True)
	# for rankIdx, (_, docObj) in enumerate(scoredDocs[:5]):
	# 	print(f"순위 {rankIdx+1}", flush=True)
	# 	print("제목:", docObj.get("title"), flush=True)
	# 	print("URL:", docObj.get("url"), flush=True)

	# ==========================
	# 5️⃣ RERANK
	# ==========================
	rerankList = []

	for docObj in candidateList:
		embedText = docObj.get("text", "")
		rerankList.append([queryStr, embedText])
	
	t_rerank = time.time()
	scoreList = rerankModel.predict(rerankList)
	print(f"[PERF] reranker ({len(rerankList)}쌍): {time.time()-t_rerank:.3f}s", flush=True)
	scoredDocs = list(zip(scoreList, candidateList))
	scoredDocs.sort(key=lambda item: item[0], reverse=True)

	print("===== RERANK 결과 =====", flush=True)

	for rankIdx, (scoreVal, docObj) in enumerate(scoredDocs[:20]):
		print(f"RERANK 순위 {rankIdx+1} / 점수 {scoreVal:.4f}", flush=True)
		print("제목:", docObj.get("title"), flush=True)
		print("URL:", docObj.get("url"), flush=True)
		print("내용 전체:", docObj.get("text", ""), flush=True)


	# =====================================================
	# RERANK 점수 threshold 검사 (추가)
	# =====================================================

	# RERANK_THRESHOLD = 1.0   # 경험값, 로그 보고 조정

	# scoredDocs = [(s, d) for s, d in scoredDocs if s >= RERANK_THRESHOLD]

	if len(scoredDocs) == 0:

		print("관련 문서 없음 → RAG 중단", flush=True)
		print("===== RAG 검색 종료 =====", flush=True)

		return "", [], scoredDocs


	# ------------------------------
	# 6️⃣ 최종 Top 문서 선택
	# ------------------------------
	topDocs = []
	topScored = scoredDocs[:5]
	for scoreVal, docObj in scoredDocs[:5]:
		topDocs.append(docObj)

	contextText = ""


	# ------------------------------
	# 7️⃣ LLM 전달 Context 생성
	# ------------------------------
	for idx, docObj in enumerate(topDocs, start=1):
		contextText += f"""
		[{idx}] 제목: {docObj.get('title')}
		내용:
		{docObj.get('text')}
		"""

	print("최종 선택 문서 개수:", len(topDocs), flush=True)

	print("===== RAG 검색 종료 =====", flush=True)

	if DEBUG_SEARCH_LOG:
		from rag.search_logger import log_search
		log_search(queryStr, queryVec, distances, indices, candidateList, topScored, topDocs, rerankList)

	return contextText, topDocs, topScored


# =====================================================
# LLM 답변 기반 출처 매칭
# =====================================================

def match_source(answerText, topDocs):

	print("===== 출처 매칭 시작 =====", flush=True)

	sourceUrl = []	
	sourceSet = set()   # ⭐ 중복 URL 방지용 set 추가

	answerClean = answerText.replace(" ", "")

	# ------------------------------
	# 문서가 없는 경우 출처 표시 안함
	# ------------------------------
	if len(topDocs) == 0:

		print("출처 문서 없음", flush=True)
		return sourceUrl

	# ------------------------------
	# 1️⃣ 답변에 문서 일부가 포함된 경우
	# ------------------------------
	for docObj in topDocs:

		textStr = docObj.get("text", "")
		urlStr = get_source_url(docObj)

		textClean = textStr.replace(" ", "")

		if textClean[:80] in answerClean:

			# 중복 URL 방지
			if urlStr not in sourceSet:

				sourceUrl.append(urlStr)
				sourceSet.add(urlStr)

				print("출처 매칭 성공:", urlStr, flush=True)
	
	# ------------------------------
	# 2️⃣ 제목의 책 이름 키워드 매칭	
	# ------------------------------
	if len(sourceUrl) == 0:
		for docObj in topDocs:
			title = docObj.get("title", "")
			urlStr = get_source_url(docObj)
			# [새번역 마가복음서 ...] → "마가복음서"
			m = re.match(r'\[\S+\s+(\S+?)\s', title)
			if not m:
				continue
			book = m.group(1)
			book_short = book.rstrip("서")   # 마가복음서 → 마가복음
			if book_short and book_short in answerText:
				if urlStr not in sourceSet:
					sourceUrl.append(urlStr)
					sourceSet.add(urlStr)
					print("제목 키워드 매칭:", book_short, "→", urlStr, flush=True)
					
	# ------------------------------
	# 3️⃣ 매칭 실패 시 유사도 기반 선택
	# ------------------------------
	if len(sourceUrl) == 0:

		print("문장 매칭 실패 → 유사도 검사", flush=True)

		bestScore = 0
		bestUrl = ""

		for docObj in topDocs:

			textStr = docObj.get("text", "")
			urlStr = get_source_url(docObj)

			ratioVal = SequenceMatcher(None, answerText, textStr[:500]).ratio()

			if ratioVal > bestScore:

				bestScore = ratioVal
				bestUrl = urlStr

		if bestScore > 0.3 and bestUrl:

			# 중복 URL 방지
			if bestUrl not in sourceSet:

				sourceUrl.append(bestUrl)
				sourceSet.add(bestUrl)

				print("유사도 기반 선택:", bestUrl, flush=True)

	print("최종 출처:", sourceUrl, flush=True)

	return sourceUrl

def parse_title(title: str):
    m = re.match(r'\[(\S+)\s+(\S+)\s+(\d+)장\s+(\d+)절\]', title)
    if m:
        return m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
    return None


def get_surrounding_docs(version: str, book: str, chap: int, sec: int, window: int = 5) -> list:
    prefix = f"[{version} {book} {chap}장"
    sec_min = max(1, sec - window)
    sec_max = sec + window

    result = []
    for doc in vdb_bible.docsList:
        title = doc.get("title", "")
        if not title.startswith(prefix):
            continue
        m = re.search(r'(\d+)절', title)
        if m and sec_min <= int(m.group(1)) <= sec_max:
            result.append((int(m.group(1)), doc))

    return [doc for _, doc in sorted(result, key=lambda x: x[0])]


def normalize_distance(scoreVal):
    distanceVal = 1 / (1 + math.exp(-scoreVal))

    if distanceVal < 0:
        distanceVal = 0.0

    if distanceVal > 1:
        distanceVal = 1.0

    return round(distanceVal, 4)


def build_doc_sources(finalResults):
    docSources = []

    for scoreVal, docObj in finalResults:
        fileName = docObj.get("file")
        pageNum = docObj.get("page")
        textStr = docObj.get("text", "")

        if not fileName or not textStr:
            continue

        metadataObj = {
            "source": fileName,
            "name": fileName,
        }

        if pageNum is not None:
            metadataObj["page"] = pageNum

        encoded_name = quote(fileName)
        page = pageNum if pageNum is not None else 1

        docSources.append({
            "source": {
                "name": fileName,
                "id": fileName,
                "url": get_source_url(docObj)
            },
            "document": [textStr],
            "metadata": [metadataObj],
            "distances": [normalize_distance(scoreVal)],
        })

    return docSources
