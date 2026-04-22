import faiss
import pickle
import os
import numpy as np

dimensionNum = 1024

# 문서 업로드 전용 DB
indexFile = "/data/faiss_pdf.index"
docsFile = "/data/docs_pdf.pkl"


if os.path.exists(indexFile):

	indexObjDoc = faiss.read_index(indexFile)

	with open(docsFile, "rb") as fileObj:

		docsListDoc = pickle.load(fileObj)

	print("기존 Document VectorDB 로드:", len(docsListDoc), flush=True)

else:

	baseIndex = faiss.IndexFlatIP(dimensionNum)
	indexObjDoc = faiss.IndexIDMap(baseIndex)

	docsListDoc = []

	print("새 Document VectorDB 생성", flush=True)


def add_vector_doc(vectorArr, textStr, fileNameStr,
                   pageNum=None, chunkIndex=0, sourceType="file",
                   metadata=None):  # dict로 유연하게

	vectorArr = np.array(vectorArr).astype("float32")

	docId = len(docsListDoc)

	indexObjDoc.add_with_ids(vectorArr, np.array([docId]))

	docsListDoc.append({
		"text": textStr,
		"file": fileNameStr,
		"title": fileNameStr,
		"page": pageNum,
		"chunk_index": chunkIndex,
		"source_type": sourceType,
		**(metadata or {}),
	})

	print("Document Vector 저장:", len(docsListDoc), flush=True)


def save_index_doc():

	faiss.write_index(indexObjDoc, indexFile)

	with open(docsFile, "wb") as fileObj:

		pickle.dump(docsListDoc, fileObj)

	print("Document VectorDB 저장 완료", flush=True)

def reset_index_doc():
    global indexObjDoc, docsListDoc
    if os.path.exists(indexFile):
        os.remove(indexFile)
    if os.path.exists(docsFile):
        os.remove(docsFile)
    baseIndex = faiss.IndexFlatIP(dimensionNum)
    indexObjDoc = faiss.IndexIDMap(baseIndex)
    docsListDoc = []
    print("Document VectorDB 초기화 완료", flush=True)

def remove_by_file(fileNameStr):
    """특정 파일의 벡터를 인덱스와 docsList에서 삭제"""
    ids_to_remove = [
        idx for idx, doc in enumerate(docsListDoc)
        if doc is not None and doc.get("file") == fileNameStr
    ]
    if not ids_to_remove:
        print(f"[{fileNameStr}] 삭제할 벡터 없음", flush=True)
        return

    # FAISS 인덱스에서 제거
    indexObjDoc.remove_ids(np.array(ids_to_remove, dtype=np.int64))

    # docsList는 인덱스 순서 유지 필요 (docId = list index)
    # → 해당 위치를 None으로 마킹 (삭제하면 뒤쪽 ID 전부 틀어짐)
    for idx in ids_to_remove:
        docsListDoc[idx] = None

    print(f"[{fileNameStr}] {len(ids_to_remove)}건 삭제 완료", flush=True)