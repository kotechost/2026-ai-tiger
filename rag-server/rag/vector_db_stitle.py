import faiss
import pickle
import os
import numpy as np

dimensionNum = 1024

indexFile = "/data/faiss_stitle.index"
docsFile  = "/data/docs_stitle.pkl"


# 기존 index 로드
if os.path.exists(indexFile):

	indexObj = faiss.read_index(indexFile)

	with open(docsFile, "rb") as fileObj:

		docsList = pickle.load(fileObj)

	print("기존 stitle VectorDB 로드:", len(docsList), flush=True)

else:

	baseIndex = faiss.IndexFlatIP(dimensionNum)
	indexObj = faiss.IndexIDMap(baseIndex)

	docsList = []

	print("새 stitle VectorDB 생성", flush=True)


def add_vector(vectorArr, textStr, urlStr, titleStr, smallTitleStr=""):

    vectorArr = np.array(vectorArr).astype("float32")
    docId = len(docsList)
    indexObj.add_with_ids(vectorArr, np.array([docId]))

    docsList.append({
        "text":        textStr,
        "url":         urlStr,
        "title":       titleStr,
        "small_title": smallTitleStr
    })

    print("Vector 저장:", len(docsList), flush=True)


def add_vectors_batch(vectorsArr, docDictList):
    startId = len(docsList)
    ids = np.arange(startId, startId + len(docDictList))
    indexObj.add_with_ids(vectorsArr, ids)
    docsList.extend(docDictList)
    print(f"Vector 배치 저장: {len(docsList)}건", flush=True)


def save_index():

	faiss.write_index(indexObj, indexFile)

	with open(docsFile, "wb") as fileObj:

		pickle.dump(docsList, fileObj)

	print("VectorDB 저장 완료", flush=True)


def reset_index():
    global indexObj, docsList
    if os.path.exists(indexFile):
        os.remove(indexFile)
    if os.path.exists(docsFile):
        os.remove(docsFile)
		
    baseIndex = faiss.IndexFlatIP(dimensionNum)
    indexObj = faiss.IndexIDMap(baseIndex)
    docsList = []
    print("VectorDB 초기화 완료", flush=True)


