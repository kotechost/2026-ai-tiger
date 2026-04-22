from sentence_transformers import SentenceTransformer
import numpy as np

#modelObj = SentenceTransformer("BAAI/bge-m3")

# intfloat/multilingual-e5-large

modelObj = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")

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

def get_embeddings_batch(textList: list, typeStr="passage"):
    prefixed = [
        ("query: " if typeStr == "query" else "passage: ") + t
        for t in textList
    ]

    chunkSize = 5000
    allVectors = []

    for i in range(0, len(prefixed), chunkSize):
        chunk = prefixed[i:i + chunkSize]
        print(f"[embedding] {i + len(chunk)}/{len(prefixed)}건 처리 중...", flush=True)
        vectors = modelObj.encode(chunk, batch_size=256, show_progress_bar=False)
        allVectors.append(vectors)

    vectors = np.vstack(allVectors)
    vectors = np.array(vectors).astype("float32")
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors
