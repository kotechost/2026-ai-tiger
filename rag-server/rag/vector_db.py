import faiss
import pickle
import os
import numpy as np

dimensionNum = 1024

indexFile = "/data/faiss.index"
docsFile = "/data/docs.pkl"


# 기존 index 로드
if os.path.exists(indexFile):

	indexObj = faiss.read_index(indexFile)

	with open(docsFile, "rb") as fileObj:

		docsList = pickle.load(fileObj)

	print("기존 VectorDB 로드:", len(docsList), flush=True)

else:

	baseIndex = faiss.IndexFlatIP(dimensionNum)
	indexObj = faiss.IndexIDMap(baseIndex)

	docsList = []

	print("새 VectorDB 생성", flush=True)


def add_vector(vectorArr, textStr, urlStr, titleStr):

	vectorArr = np.array(vectorArr).astype("float32")

	docId = len(docsList)

	indexObj.add_with_ids(vectorArr, np.array([docId]))

	docsList.append({
		"text": textStr,
		"url": urlStr,
		"title": titleStr
	})

	print("Vector 저장:", len(docsList), flush=True)


def save_index():

	faiss.write_index(indexObj, indexFile)

	with open(docsFile, "wb") as fileObj:

		pickle.dump(docsList, fileObj)

	print("VectorDB 저장 완료", flush=True)