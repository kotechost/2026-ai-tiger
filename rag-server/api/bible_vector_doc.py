import asyncio
from fastapi import APIRouter, UploadFile, Form
from rag.pdf_parser import parse_pdf_to_page_items
from rag.document_to_vector import document_to_vector
from rag.vector_db_doc import reset_index_doc, remove_by_file

router = APIRouter(tags=["DocVector"])


@router.post("/v1/documents",
    summary="문서 업로드 → VectorDB 저장",
)
async def upload_document(file: UploadFile, parser_name: str = Form("fitz")):
    print(f"📂 문서 업로드: {file.filename}", flush=True)
    content = await file.read()
    fileNameStr = file.filename or "unknown"

    if not fileNameStr.lower().endswith(".pdf"):
        return {"status": "error", "message": "PDF 파일만 지원합니다."}
    
    
    # 업로드 파일을 /app/pdfs에 저장 (호스트 ./rag-server/pdfs/ 에서 확인 가능)
    save_path = f"/app/pdfs/{fileNameStr}"
    with open(save_path, "wb") as f:
        f.write(content)
 
    # 1. 파싱 (헤딩 기반 섹션 분할 + 청킹)
    pageItemList = parse_pdf_to_page_items(content, parser_name)
 
    if not pageItemList:
        return {"status": "error", "message": "텍스트 추출 실패"}
 
    # 2. 같은 파일명 기존 벡터만 삭제 후 추가
    remove_by_file(fileNameStr)
    document_to_vector(pageItemList, fileNameStr)

    return {"status": "ok", "filename": fileNameStr, "pages": len(pageItemList)}
