import csv
import json
from pathlib import Path

from rag.search_doc import search_document


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV_PATH = BASE_DIR / "data" / "retrieval_eval_queries.csv"
OUTPUT_JSON_PATH = BASE_DIR / "data" / "retrieval_result.json"
SUMMARY_JSON_PATH = BASE_DIR / "data" / "retrieval_summary.json"


def reciprocal_rank(rank):
    if rank is None:
        return 0.0
    return 1.0 / rank


def match_page(retrieved_page, ground_truth_page):
    return retrieved_page == ground_truth_page


def find_rank(items, matcher):
    for item in items:
        if matcher(item):
            return item["rank"]
    return None


def build_metric_block(rank):
    return {
        "ground_truth_rank": rank,
        "hit_at_1": rank == 1,
        "hit_at_3": rank is not None and rank <= 3,
        "hit_at_5": rank is not None and rank <= 5,
        "reciprocal_rank": round(reciprocal_rank(rank), 6),
    }


def convert_results_to_items(results):
    items = []

    for rank, (score, doc_obj) in enumerate(results[:5], start=1):
        page_num_internal = doc_obj.get("page")
        page_num_human = None if page_num_internal is None else page_num_internal + 1

        items.append(
            {
                "rank": rank,
                "page": page_num_human,
                "score": round(float(score), 6),
                "file": doc_obj.get("file"),
                "text_preview": doc_obj.get("text", "")[:200],

                # 나중에 metadata 설계 후 사용
                # "department": doc_obj.get("department"),
                # "section": doc_obj.get("section"),
            }
        )

    return items


def evaluate_retrieval(input_csv_path=INPUT_CSV_PATH):
    results = []

    with open(input_csv_path, "r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)

        for row_idx, row in enumerate(reader, start=1):
            query = row["query"].strip()
            ground_truth_page = int(row["ground_truth_page"])

            print("=" * 80, flush=True)
            print(f"[{row_idx}] 평가 질문: {query}", flush=True)
            print(f"GT page={ground_truth_page}", flush=True)

            search_result = search_document(query, debug=True)

            before_rerank_results = search_result["before_rerank_results"]
            after_rerank_results = search_result["after_rerank_results"]

            before_items = convert_results_to_items(before_rerank_results)
            after_items = convert_results_to_items(after_rerank_results)

            before_page_rank = find_rank(
                before_items,
                lambda item: match_page(item["page"], ground_truth_page),
            )
            after_page_rank = find_rank(
                after_items,
                lambda item: match_page(item["page"], ground_truth_page),
            )

            result_item = {
                "query": query,
                "ground_truth": {
                    "page": ground_truth_page,

                    # 나중에 metadata 설계 후 사용
                    # "department": row.get("ground_truth_department", "").strip(),
                    # "section": row.get("ground_truth_section", "").strip(),
                    # "answer_type": row.get("answer_type", "").strip(),
                },
                "retrieval_before_rerank": before_items,
                "retrieval_after_rerank": after_items,
                "metrics": {
                    "before_rerank": {
                        "page": build_metric_block(before_page_rank),

                        # 나중에 metadata 설계 후 사용
                        # "department": build_metric_block(before_department_rank),
                        # "section": build_metric_block(before_section_rank),
                    },
                    "after_rerank": {
                        "page": build_metric_block(after_page_rank),

                        # 나중에 metadata 설계 후 사용
                        # "department": build_metric_block(after_department_rank),
                        # "section": build_metric_block(after_section_rank),
                    },
                },
            }

            results.append(result_item)

            print(
                f"before page rank={before_page_rank}, after page rank={after_page_rank}",
                flush=True,
            )

    return results


def summarize_metric(results, stage, metric_key):
    valid_items = []

    for item in results:
        metric_obj = item["metrics"][stage].get(metric_key)
        if metric_obj is not None:
            valid_items.append(metric_obj)

    total = len(valid_items)

    if total == 0:
        return None

    hit_at_1 = sum(1 for item in valid_items if item["hit_at_1"])
    hit_at_3 = sum(1 for item in valid_items if item["hit_at_3"])
    hit_at_5 = sum(1 for item in valid_items if item["hit_at_5"])
    mrr = sum(item["reciprocal_rank"] for item in valid_items) / total

    return {
        "total": total,
        "hit_at_1": round(hit_at_1 / total, 4),
        "hit_at_3": round(hit_at_3 / total, 4),
        "hit_at_5": round(hit_at_5 / total, 4),
        "mrr": round(mrr, 4),
    }


def build_summary(results):
    return {
        "total": len(results),

        # 임베딩 모델 비교용
        "before_rerank": {
            "page": summarize_metric(results, "before_rerank", "page"),
        },

        # 전체 검색 파이프라인 비교용
        "after_rerank": {
            "page": summarize_metric(results, "after_rerank", "page"),
        },

        # 나중에 metadata 설계 후 사용
        # "by_answer_type": summarize_by_answer_type(results),
    }


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, ensure_ascii=False, indent=2)


def main():
    results = evaluate_retrieval()
    summary = build_summary(results)

    save_json(OUTPUT_JSON_PATH, results)
    save_json(SUMMARY_JSON_PATH, summary)

    print("=" * 80, flush=True)
    print("평가 완료", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
