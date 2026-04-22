from rag.chunk import split_text
from rag.embedding import get_embedding

from rag.vector_db_doc import add_vector_doc, save_index_doc


def document_to_vector(pageItemList, fileNameStr, sourceType="file"):

    totalChunkCount = 0

    for pageItem in pageItemList:
        pageNum = pageItem.get("page")
        textStr = pageItem.get("text", "")
        department = pageItem.get("department", "")
        college = pageItem.get("college", "")
        chunkList = split_text(textStr)

        for chunkIndex, chunkStr in enumerate(chunkList):
            embedText = f"""
            문서명: {fileNameStr}
            대학: {college}
            학과: {department}
            페이지: {pageNum}
            내용:
            {chunkStr}
            """
            vectorArr = get_embedding(embedText, "passage")
            add_vector_doc(vectorArr, chunkStr, fileNameStr,
                           pageNum=pageNum, chunkIndex=chunkIndex,
                           sourceType=sourceType,
                           department=department, college=college)

            totalChunkCount += 1

    save_index_doc()

    print("총 문서 chunk 개수:", totalChunkCount, flush=True)
    print("===== 문서 Vector 저장 완료 =====", flush=True)
