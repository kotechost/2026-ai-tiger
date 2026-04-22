from sentence_transformers import SentenceTransformer
import numpy as np

#modelObj = SentenceTransformer("BAAI/bge-m3")

# intfloat/multilingual-e5-large

modelObj = SentenceTransformer("intfloat/multilingual-e5-large")

def get_embedding(textStr: str, typeStr="passage"):

	if typeStr == "query":
		textStr = "query: " + textStr
	else:
		textStr = "passage: " + textStr

	vectorArr = modelObj.encode([textStr])

	vectorArr = np.array(vectorArr).astype("float32")

	# ⭐ 벡터 정규화 (검색 정확도 개선)
	vectorArr = vectorArr / np.linalg.norm(vectorArr, axis=1, keepdims=True)

	return vectorArr

# BAAI/bge-m3

# modelObj = SentenceTransformer("BAAI/bge-m3")

# def get_embedding(textStr: str, typeStr="passage"):
#     vectorArr = modelObj.encode([textStr])
#     vectorArr = np.array(vectorArr).astype("float32")
#     vectorArr = vectorArr / np.linalg.norm(vectorArr, axis=1, keepdims=True)
#     return vectorArr

