from rag.embedding import get_embedding
from rag.vector_db import indexObj, docsList
from sentence_transformers import CrossEncoder
from difflib import SequenceMatcher   # 문자열 유사도 비교

from rag.rewrite_query import rewrite_query

rerankModel = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu")


def search_context(queryStr):

	print("===== RAG 검색 시작 =====", flush=True)
	print("검색 질문:", queryStr, flush=True)

	# ------------------------------
	# ⭐ Query Rewrite 실행 (추가)
	# ------------------------------
	rewriteResult = rewrite_query(queryStr)
	# rewriteResult = None;

	# ⭐ rewrite 결과 없을 경우 기본값
	if rewriteResult is None:
		rewriteResult = {
			"type": "query",
			"data": queryStr
		}

	# ------------------------------
	# ⭐ Router 문서 반환
	# ------------------------------
	if rewriteResult["type"] == "docs":

		print("Rewrite Router 문서 사용", flush=True)

		contextText = ""

		for docObj in rewriteResult["data"]:

			contextText += f"""
			제목: {docObj.get('title')}
			URL: {docObj.get('url')}
			내용:
			{docObj.get('text')}
			"""

		print("===== RAG 검색 종료 =====", flush=True)

		return contextText, rewriteResult["data"], [], rewriteResult["data"]


	# ------------------------------
	# ⭐ 검색 질문 생성
	# ------------------------------
	queryRewrite = rewriteResult["data"]

	print("Rewrite 질문:", queryRewrite, flush=True)


	# ------------------------------
	# 1️⃣ 질문 벡터 생성 - Query Expansion
	# ------------------------------
	queryVec = get_embedding(queryRewrite, "query")


	# ------------------------------
	# 2️⃣ FAISS 검색 (후보 80개)
	# ------------------------------
	distances, indices = indexObj.search(queryVec, 80)

	print("검색 index:", indices, flush=True)

	candidateList = []

	# ------------------------------
	# 3️⃣ FAISS 검색 결과 문서 추출
	# ------------------------------
	for idxNum, idx in enumerate(indices[0]):

		if idx == -1:
			continue

		if idx < len(docsList):

			docObj = docsList[idx]
			candidateList.append(docObj)

			print("FAISS 후보 인덱스:", idx, flush=True)
			print("FAISS 후보 개수:", len(candidateList), flush=True)
			print(f"FAISS 후보[{idxNum}]:", docObj.get("text", "")[:200], flush=True)


	# ------------------------------
	# 후보 문서 없는 경우 종료
	# ------------------------------
	if len(candidateList) == 0:

		print("검색 결과 없음", flush=True)
		print("===== RAG 검색 종료 =====", flush=True)
		return "", [], [], []

	print("총 FAISS 후보 개수:", len(candidateList), flush=True)


	# =====================================================
	# 4️⃣ 문자열 기반 필터링
	# =====================================================

	filteredList = []

	queryClean = queryStr.replace(" ", "")
	queryWords = queryStr.split()

	for docObj in candidateList:

		textStr = docObj.get("text", "")
		titleStr = docObj.get("title", "")

		combinedStr = titleStr + " " + textStr
		textClean = combinedStr.replace(" ", "")

		# ------------------------------
		# 1️⃣ 공백 제거 후 전체 문자열 포함 검사
		# ------------------------------
		if queryClean in textClean:
			filteredList.append(docObj)
			continue

		# ------------------------------
		# 2️⃣ 단어 매칭 검사
		# ------------------------------
		if any(word in combinedStr for word in queryWords):
			filteredList.append(docObj)
			continue

		# ------------------------------
		# 3️⃣ 문자열 유사도 검사
		# ------------------------------
		ratioVal = SequenceMatcher(None, queryClean, textClean[:200]).ratio()

		if ratioVal > 0.25:
			filteredList.append(docObj)

	if len(filteredList) > 0:
		candidateList = filteredList

	print("필터 후 후보 개수:", len(candidateList), flush=True)


	# ==========================
	# 5️⃣ RERANK
	# ==========================
	pairList = []

	for docObj in candidateList:

		titleStr = docObj.get("title", "")
		textStr = docObj.get("text", "")

		docText = f"""
		제목: {titleStr}
		제목: {titleStr}
		제목: {titleStr}

		내용:
		{textStr}
		"""

		pairList.append([queryStr, docText])

	scoreList = rerankModel.predict(pairList)


	# ------------------------------
	# ⭐ title 기반 score boost
	# ------------------------------
	boostedScores = []

	for scoreVal, docObj in zip(scoreList, candidateList):

		titleStr = docObj.get("title", "")

		if titleStr and titleStr in queryStr:
			scoreVal = scoreVal + 0.35

		boostedScores.append(scoreVal)

	scoredDocs = list(zip(boostedScores, candidateList))

	scoredDocs.sort(key=lambda item: item[0], reverse=True)


	# =====================================================
	# ⭐ title intent 기반 강제 우선순위 적용
	# =====================================================

	queryClean = queryStr.replace(" ", "")

	titleMatched = []
	others = []

	for scoreVal, docObj in scoredDocs:

		titleStr = docObj.get("title", "")
		titleClean = titleStr.replace(" ", "")

		if titleClean and titleClean in queryClean:

			print("title intent 매칭:", titleStr, flush=True)

			scoreVal = scoreVal + 1.5
			titleMatched.append((scoreVal, docObj))

		else:

			others.append((scoreVal, docObj))

	scoredDocs = titleMatched + others


	# ------------------------------
	# 다시 정렬
	# ------------------------------

	scoredDocs.sort(key=lambda item: item[0], reverse=True)


	print("===== RERANK 결과 =====", flush=True)

	for rankIdx, (scoreVal, docObj) in enumerate(scoredDocs[:20]):
		print(f"RERANK 순위 {rankIdx+1} / 점수 {scoreVal:.4f}", flush=True)
		print("제목:", docObj.get("title"), flush=True)
		print("URL:", docObj.get("url"), flush=True)
		print("내용 전체:", docObj.get("text", ""), flush=True)


	# =====================================================
	# ⭐ RERANK 점수 threshold 검사 (추가)
	# =====================================================

	if len(scoredDocs) == 0 or scoredDocs[0][0] < 0.002:

		print("관련 문서 없음 → RAG 중단", flush=True)
		print("===== RAG 검색 종료 =====", flush=True)

		return "", [], scoredDocs, []


	# ------------------------------
	# 6️⃣ 최종 Top 문서 선택
	# ------------------------------
	topDocs = []

	for scoreVal, docObj in scoredDocs[:20]:
		topDocs.append(docObj)

	contextText = ""


	# ------------------------------
	# 7️⃣ LLM 전달 Context 생성
	# ------------------------------
	for docObj in topDocs:

		contextText += f"""
		제목: {docObj.get('title')}
		URL: {docObj.get('url')}
		내용:
		{docObj.get('text')}
		"""

	print("최종 선택 문서 개수:", len(topDocs), flush=True)


	# =====================================================
	# ⭐ 8️⃣ 추천 링크 생성 (추가 기능)
	# =====================================================

	recommendList = []
	urlSet = set()

	if len(scoredDocs) > 0:

		scoreMin = min(score for score, _ in scoredDocs)
		scoreMax = max(score for score, _ in scoredDocs)

		for scoreVal, docObj in scoredDocs:

			urlStr = docObj.get("url")

			# ⭐ URL 중복 제거
			if urlStr in urlSet:
				continue

			urlSet.add(urlStr)

			percentVal = (scoreVal - scoreMin) / (scoreMax - scoreMin + 0.00001) * 100

			recommendList.append({
				"title": docObj.get("title"),
				"url": urlStr,
				"score": int(round(percentVal))
			})

			# ⭐ 최대 5개만 추천
			if len(recommendList) >= 5:
				break

	print("===== 추천 링크 =====", flush=True)

	for recObj in recommendList:

		print(
			recObj["title"],
			recObj["url"],
			f"{recObj['score']}%",
			flush=True
		)

	print("===== RAG 검색 종료 =====", flush=True)

	return contextText, topDocs, scoredDocs, recommendList


# =====================================================
# ⭐ LLM 답변 기반 출처 매칭
# =====================================================

# =====================================================
# ⭐ LLM 답변 기반 출처 매칭
# =====================================================

def match_source(answerText, topDocs):

	print("===== 출처 매칭 시작 =====", flush=True)

	sourceUrl = []	
	sourceSet = set()   # ⭐ 중복 URL 방지용 set 추가

	answerClean = answerText.replace(" ", "")

	# ------------------------------
	# ⭐ 문서가 없는 경우 출처 표시 안함
	# ------------------------------
	if len(topDocs) == 0:

		print("출처 문서 없음", flush=True)
		return sourceUrl

	# ------------------------------
	# 1️⃣ 답변에 문서 일부가 포함된 경우
	# ------------------------------
	for docObj in topDocs:

		textStr = docObj.get("text", "")
		urlStr = docObj.get("url", "")

		textClean = textStr.replace(" ", "")

		if textClean[:80] in answerClean:

			# ⭐ 중복 URL 방지
			if urlStr not in sourceSet:

				sourceUrl.append(urlStr)
				sourceSet.add(urlStr)

				print("출처 매칭 성공:", urlStr, flush=True)

	# ------------------------------
	# 2️⃣ 매칭 실패 시 유사도 기반 선택
	# ------------------------------
	if len(sourceUrl) == 0:

		print("문장 매칭 실패 → 유사도 검사", flush=True)

		bestScore = 0
		bestUrl = ""

		for docObj in topDocs:

			textStr = docObj.get("text", "")
			urlStr = docObj.get("url", "")

			ratioVal = SequenceMatcher(None, answerText, textStr[:500]).ratio()

			if ratioVal > bestScore:

				bestScore = ratioVal
				bestUrl = urlStr

		if bestScore > 0.3 and bestUrl:

			# ⭐ 중복 URL 방지
			if bestUrl not in sourceSet:

				sourceUrl.append(bestUrl)
				sourceSet.add(bestUrl)

				print("유사도 기반 선택:", bestUrl, flush=True)

	print("최종 출처:", sourceUrl, flush=True)

	return sourceUrl