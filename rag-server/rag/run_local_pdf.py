"""
로컬 PDF → VectorDB 변환 스크립트
실행 명령어:
  python run_local_pdf.py /app/pdfs/2023_순천향대학교_요람.pdf --parser fitz
  docker compose -p llm-system-jsy exec rag-api-jsy python rag/run_local_pdf.py /app/pdfs/2023_순천향대학교_요람.pdf --parser fitz_hybrid
  docker compose -p llm-system-jsy exec -w /app rag-api-jsy python3 rag/run_local_pdf.py /app/pdfs/2023_sch_m.pdf --parser fitz_hybrid

  docker compose -p llm-system-jsy exec -w /app rag-api-jsy python3 rag/run_local_pdf.py /app/pdfs/2023_sch_m.pdf --parser fitz_qwen_vl

  docker compose -p llm-system-jsy exec -w /app rag-api-jsy \
  python3 -m rag.run_local_pdf /app/pdfs/2023_sch_m.pdf --parser fitz_qwen_vl

  # 호스트에서 간단한 요청을 보내서 모델을 미리 VRAM에 올려놓기
  curl http://localhost:11436/api/chat -d '{"model":"qwen2.5vl:7b","messages":[{"role":"user","content":"hello"}],"stream":false}'
  curl http://localhost:11436/api/chat -d '{"model":"qwen2.5vl:3b","messages":[{"role":"user","content":"hello"}],"stream":false}'

"""
import argparse
import sys
from pathlib import Path

from rag.pdf_parser import parse_pdf_to_page_items
from rag.document_to_vector import document_to_vector


def main():
    # 기존 VectorDB 초기화
    from rag.vector_db_doc import indexObjDoc, docsListDoc
    indexObjDoc.reset()
    docsListDoc.clear()
    print("기존 Document VectorDB 초기화", flush=True)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    parser.add_argument("--parser", default="fitz")
    args = parser.parse_args()

    pdf_path = Path(args.file_path)
    if not pdf_path.exists():
        print(f"파일 없음: {args.file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"파일: {pdf_path.name}, 파서: {args.parser}", flush=True)

    content = pdf_path.read_bytes()
    pageItemList = parse_pdf_to_page_items(content, parser_name=args.parser)

    print(f"추출 페이지: {len(pageItemList)}", flush=True)

    if not pageItemList:
        print("텍스트 추출 실패", file=sys.stderr)
        sys.exit(1)

    document_to_vector(pageItemList, pdf_path.name)

    for item in pageItemList:
        page = item["page"]
        text = item["text"]
        meta = item.get("metadata", {})
        print(f"\n{'='*60}", flush=True)
        print(f"[page={page}] 글자수={len(text)} meta={meta}", flush=True)
        print(f"{'─'*60}", flush=True)
        print(text[:300], flush=True)
        if len(text) > 300:
            print("...", flush=True)


if __name__ == "__main__":
    main()
