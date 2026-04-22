from rag.vector_db import docsList


def rewrite_query(queryStr):

	print("===== Query Rewrite 시작 =====", flush=True)

	queryClean = queryStr.replace(" ", "").lower()

	# ------------------------------
	# 진천 지사 관련 질문
	# ------------------------------
	if (
		"진천지사" in queryClean
		or "충북지사" in queryClean
		or "지사위치" in queryClean
		or "jincheon" in queryClean
	):

		print("Query Rewrite: 진천 지사 질문 확장", flush=True)

		return {
			"type": "query",
			"data": "코테크시스템 진천 지사 위치 주소 오시는길 연락처 충북 진천 코테크 지사"
		}

