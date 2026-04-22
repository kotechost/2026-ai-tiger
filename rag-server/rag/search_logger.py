import os
import json
from datetime import datetime

SEARCH_LOG_FILE = "/data/search_analysis_log.json"


def log_search(queryStr, queryVec, distances, indices, candidateList, scoredDocs, topDocs, pairList):
    searchLog = {
        "query":     queryStr,
        "timestamp": datetime.now().isoformat(),
        "query_vector": queryVec[0].tolist(),
        "faiss": {
            "distances": distances[0].tolist(),
            "indices":   indices[0].tolist(),
        },
        "candidates": [
            {
                "title": doc.get("title"),
                "text":  doc.get("text", "")[:100]
            }
            for doc in candidateList
        ],
        "rerank_input": [
            {"query": pair[0], "doc": pair[1][:200]}
            for pair in pairList
        ] if pairList else [],
        "rerank": [
            {
                "rank":  i + 1,
                "score": round(float(score), 4),
                "title": doc.get("title"),
                "url":   doc.get("url"),
                "text":  doc.get("text", "")[:100]
            }
            for i, (score, doc) in enumerate(scoredDocs[:10])
        ],
        "top_docs": [
            {
                "title": doc.get("title"),
                "url":   doc.get("url"),
                "text":  doc.get("text", "")[:100]
            }
            for doc in topDocs
        ]
    }

    existingLogs = []
    if os.path.exists(SEARCH_LOG_FILE):
        with open(SEARCH_LOG_FILE, "r", encoding="utf-8") as f:
            existingLogs = json.load(f)

    existingLogs.append(searchLog)

    with open(SEARCH_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(existingLogs, f, ensure_ascii=False, indent=2)
