import faiss
import pickle
import os
import numpy as np

dimensionNum = 1024

# ⭐ 문서 업로드 전용 DB
indexFile = "/data/doc_faiss_e5_pars_qwen_vl_hybrid.index"
docsFile = "/data/doc_docs_e5_pars_qwen_vl_hybrid.pkl"


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
                       department="", college=""):

	vectorArr = np.array(vectorArr).astype("float32")

	docId = len(docsListDoc)

	indexObjDoc.add_with_ids(vectorArr, np.array([docId]))

	docsListDoc.append({
		"text": textStr,
		"file": fileNameStr,
		"title": fileNameStr,
		"source": fileNameStr,
		"page": pageNum,
		"chunk_index": chunkIndex,
		"source_type": sourceType,
		"department": department,
		"college": college,
	})

	print("Document Vector 저장:", len(docsListDoc), flush=True)


def save_index_doc():

	faiss.write_index(indexObjDoc, indexFile)

	with open(docsFile, "wb") as fileObj:

		pickle.dump(docsListDoc, fileObj)

	print("Document VectorDB 저장 완료", flush=True)