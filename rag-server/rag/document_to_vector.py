from rag.chunk import split_text
from rag.embedding import get_embedding

from rag.vector_db_doc import add_vector_doc, save_index_doc

import json
import os


VECTOR_DUMP_FILE = "/data/vectorize_dump_pdf.json"

def document_to_vector(pageItemList, fileNameStr, sourceType="file"):
    totalChunkCount = 0
    dumpEntries = []  # dump용

    for pageItem in pageItemList:
        pageNum = pageItem.get("page")+1
        textStr = pageItem.get("text", "")
        h1 = pageItem.get("h1", "")
        h2 = pageItem.get("h2", "")
        h3 = pageItem.get("h3", "")

        chunkList = split_text(textStr)

        for chunkIndex, chunkStr in enumerate(chunkList):
            embedText = f"""
대단원: {h1}
중단원: {h2}
소단원: {h3}
페이지: {pageNum}
내용:
{chunkStr}
""".strip()

            vectorArr = get_embedding(embedText, "passage")
            add_vector_doc(
                vectorArr, chunkStr, fileNameStr,
                pageNum=pageNum, chunkIndex=chunkIndex,
                sourceType=sourceType,
                metadata={"h1": h1, "h2": h2, "h3": h3},
            )
            totalChunkCount += 1

            # dump 데이터 수집
            dumpEntries.append({
                "index": totalChunkCount - 1,
                "embedText": embedText,
                "file": fileNameStr,
                "page": pageNum,
                "chunk_index": chunkIndex,
                "대단원": h1,
                "중단원": h2,
                "소단원": h3,
                "내용": chunkStr
            })

    save_index_doc()

    existing = []
    if os.path.exists(VECTOR_DUMP_FILE):
        with open(VECTOR_DUMP_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    
    existing = [e for e in existing if e.get("file") != fileNameStr]

    with open(VECTOR_DUMP_FILE, "w", encoding="utf-8") as f:
        json.dump(existing + dumpEntries, f, ensure_ascii=False, indent=2)


    print("총 문서 chunk 개수:", totalChunkCount, flush=True)
    print("===== 문서 Vector 저장 완료 =====", flush=True)
