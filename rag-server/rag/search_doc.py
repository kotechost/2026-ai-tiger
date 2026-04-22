import math

from rag.embedding import get_embedding
from rag.vector_db_doc import indexObjDoc, docsListDoc
from sentence_transformers import CrossEncoder

rerankModel = CrossEncoder("BAAI/bge-reranker-v2-m3")


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

        docSources.append({
            "source": {
                "name": fileName,
                "id": fileName,
            },
            "document": [textStr],
            "metadata": [metadataObj],
            "distances": [normalize_distance(scoreVal)],
        })

    return docSources


def empty_result(debug=False):
    if debug:
        return {
            "context_text": "",
            "top_docs": [],
            "before_rerank_results": [],
            "after_rerank_results": [],
            "final_results": [],
            "doc_sources": [],
        }

    return "", [], [], []


def search_document(queryStr, debug=False):
    print("===== 문서 RAG 검색 시작 =====", flush=True)
    print("검색 질문:", queryStr, flush=True)

    queryVec = get_embedding(queryStr, "query")

    # ------------------------------
    # 문서 VectorDB 검색
    # ------------------------------
    distances, indices = indexObjDoc.search(queryVec, 20)

    print("문서 검색 index:", indices, flush=True)

    candidateList = []
    faissResults = []

    for idxNum, idx in enumerate(indices[0]):
        if idx == -1:
            continue

        if idx < len(docsListDoc):
            docObj = docsListDoc[idx]
            scoreVal = float(distances[0][idxNum])

            candidateList.append(docObj)
            faissResults.append((scoreVal, docObj))

            print("문서 후보 인덱스:", idx, flush=True)
            print("문서 후보 개수:", len(candidateList), flush=True)
            print("FAISS 점수:", scoreVal, flush=True)
            print(f"문서 후보[{idxNum}]:", docObj.get("text", "")[:200], flush=True)

    if len(candidateList) == 0:
        print("문서 검색 결과 없음", flush=True)
        return empty_result(debug=debug)

    print("문서 후보 총 개수:", len(candidateList), flush=True)

    # ------------------------------
    # RERANK
    # ------------------------------
    pairList = []

    for docObj in candidateList:
        textStr = docObj.get("text", "")
        fileName = docObj.get("file", "")
        pageNum = docObj.get("page")
        department = docObj.get("department", "")
        college = docObj.get("college", "")

        docText = f"""
        파일: {fileName}
        대학: {college}
        학과: {department}
        페이지: {pageNum}
        내용:
        {textStr}
        """

        pairList.append([queryStr, docText])

    scoreList = rerankModel.predict(pairList)

    rerankedResults = list(zip(scoreList, candidateList))

    # 학과명 부스트: 질문에 학과명이 포함되면 해당 학과 문서 점수 +2.0 
    boostedResults = []
    for scoreVal, docObj in rerankedResults:
        dept = docObj.get("department", "")
        if dept and dept in queryStr:
            scoreVal = float(scoreVal) + 2.0
        boostedResults.append((float(scoreVal), docObj))

    rerankedResults = boostedResults
    rerankedResults.sort(key=lambda item: item[0], reverse=True)

    print("===== 문서 RERANK 결과 =====", flush=True)

    for rankIdx, (scoreVal, docObj) in enumerate(rerankedResults[:20]):
        print(f"문서 RERANK {rankIdx+1} / 점수 {scoreVal:.4f}", flush=True)
        print("파일:", docObj.get("file"), flush=True)
        print("페이지:", docObj.get("page"), flush=True)

    # ------------------------------
    # threshold
    # ------------------------------
    finalResults = []

    if len(rerankedResults) == 0 or rerankedResults[0][0] < 0.005:
        print("관련 문서 없음", flush=True)
    else:
        finalTopK = 5
        finalResults = rerankedResults[:finalTopK]

    topDocs = []
    contextText = ""

    for rankIdx, (scoreVal, docObj) in enumerate(finalResults, start=1):
        topDocs.append(docObj)

        fileName = docObj.get("file")
        pageNum = docObj.get("page")
        textStr = docObj.get("text", "")

        pageLine = ""
        if pageNum is not None:
            pageLine = f"\n페이지: {pageNum + 1}"

        department = docObj.get("department", "")
        college = docObj.get("college", "")
        deptLine = f"\n대학: {college}\n학과: {department}" if department else ""

        contextText += f"""
[문서 {rankIdx}]
파일: {fileName}{pageLine}{deptLine}
내용:
{textStr}

"""

    docSources = build_doc_sources(finalResults)

    print("===== 문서 RAG 검색 종료 =====", flush=True)

    if debug:
        return {
            "context_text": contextText,
            "top_docs": topDocs,
            "before_rerank_results": faissResults,
            "after_rerank_results": rerankedResults,
            "final_results": finalResults,
            "doc_sources": docSources,
        }

    return contextText, topDocs, rerankedResults, docSources
