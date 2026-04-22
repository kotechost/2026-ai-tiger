#!/usr/bin/env python3
"""OCR 결과 분석 스크립트 - PDF 원본 대비 인식률 비교"""

import pickle
import re
import sys

# ============================================================
# 실행명령어
# docker exec llm-system-jsy-rag-api-jsy-1 python3 /app/rag/analyze_ocr.py
# 로컬복사
# docker cp llm-system-jsy-rag-api-jsy-1:/app/data/ocr_analysis_result_7b_8b.txt /mnt/hdd22t/solihost/ai/llm-system-jsy/rag-server/data
# ============================================================

# ============================================================
# 설정: 여기에 결과 파일을 원하는만큼 추가
# ============================================================
RESULT_FILES = {
    "7b_m4": "/data/doc_docs_e5_pars_qwen_vl_7b.pkl",
    "8b_m4": "/data/doc_docs_e5_pars_qwen_vl_8b_matrix4.pkl",
    "7b_8b": "/data/doc_docs_e5_pars_qwen_vl_hybrid.pkl",
    # 추가 예시:
    # "7b_m5": "/data/doc_docs_e5_pars_qwen_vl_7b_matrix5.pkl",
    # "3b":    "/data/doc_docs_e5_pars_qwen_vl.pkl",
}

PDF_PATH = "/app/pdfs/2023_sch_m.pdf"
OUTPUT_FILE = "/app/data/ocr_analysis_result_7b_8b.txt"

# ============================================================
# 반복 할루시네이션 패턴 (정상 아닌 글자로 판단)
# ============================================================
def count_hallucination_chars(text):
    """반복 패턴에 해당하는 글자수 반환"""
    total = 0
    # 같은 단어가 | 로 5회 이상 반복
    for m in re.finditer(r'((\S+)(\s*\|\s*\2){4,})', text):
        total += len(m.group(0))
    return total

def count_zero_hallucination(text):
    """0만 반복되는 패턴 글자수"""
    total = 0
    for m in re.finditer(r'((\|\s*0\s*){5,})', text):
        total += len(m.group(0))
    return total

def is_meaningful_char(c):
    """의미 있는 글자인지 (공백, 구분자 제외)"""
    return c not in ' \t\n|─-'

# ============================================================
# PDF 페이지 정보 추출 (fitz 필요)
# ============================================================
def get_pdf_page_info(pdf_path):
    """각 페이지의 텍스트/이미지 여부와 기본 텍스트 반환"""
    try:
        import fitz
    except ImportError:
        print("WARNING: pymupdf 없음 - Docker 컨테이너에서 실행하세요", file=sys.stderr)
        return None

    info = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text() or ""
            images = page.get_images(full=True)
            page_area = page.rect.width * page.rect.height
            
            img_area = 0
            for img in images:
                try:
                    bbox = page.get_image_bbox(img[7])
                    img_area += bbox.get_area()
                except:
                    pass
            
            img_ratio = (img_area / page_area * 100) if page_area > 0 else 0
            
            if img_ratio >= 50:
                page_type = "이미지"
            elif img_ratio >= 10:
                page_type = "혼합"
            else:
                page_type = "텍스트"
            
            info.append({
                "page": i,
                "pdf_page": i + 1,
                "type": page_type,
                "img_ratio": round(img_ratio, 1),
                "base_text_len": len(text.strip()),
                "base_text": text.strip()
            })
    return info

# ============================================================
# PKL 결과 로드
# ============================================================
def load_pkl(path):
    with open(path, 'rb') as f:
        return pickle.load(f)

def get_page_text(data, page_num):
    """해당 페이지의 전체 텍스트 합치기"""
    chunks = [d for d in data if d.get('page') == page_num]
    return " ".join(d.get('text', '') for d in chunks), len(chunks)

# ============================================================
# 인식률 계산
# ============================================================
def calc_recognition_rate(text):
    """정상 글자수 / 총 글자수 (할루시네이션 제외)"""
    total_chars = sum(1 for c in text if is_meaningful_char(c))
    if total_chars == 0:
        return 0, 0, 0.0
    
    halluc_chars = count_hallucination_chars(text)
    zero_chars = count_zero_hallucination(text)
    bad_chars = halluc_chars + zero_chars
    
    good_chars = max(0, total_chars - bad_chars)
    rate = (good_chars / total_chars * 100) if total_chars > 0 else 0
    
    return good_chars, total_chars, rate

# ============================================================
# 메인
# ============================================================
def main():
    # PDF 정보 (fitz 없으면 None)
    pdf_info = get_pdf_page_info(PDF_PATH)
    
    # 결과 파일 로드
    results = {}
    for label, path in RESULT_FILES.items():
        try:
            results[label] = load_pkl(path)
            print(f"로드 완료: {label} ({path})", file=sys.stderr)
        except FileNotFoundError:
            print(f"파일 없음: {path}", file=sys.stderr)
    
    if not results:
        print("로드된 결과 파일이 없습니다.", file=sys.stderr)
        return
    
    # 전체 페이지 수 계산
    max_page = 0
    for data in results.values():
        for d in data:
            max_page = max(max_page, d.get('page', 0))
    
    # 결과 생성
    lines = []
    labels = list(results.keys())
    
    # 헤더
    lines.append("=" * 120)
    lines.append(f"OCR 결과 분석 리포트 - {PDF_PATH}")
    lines.append("=" * 120)
    lines.append("")
    
    # 요약 헤더
    header = f"{'Page':>4} | {'PDF':>3} | {'유형':>4}"
    for label in labels:
        header += f" | {label+' 청크':>8} | {label+' 글자':>10} | {label+' 인식률':>10}"
    lines.append(header)
    lines.append("-" * len(header))
    
    # 페이지별 분석
    summary = {label: {"good": 0, "total": 0} for label in labels}
    
    for page_num in range(max_page + 1):
        # 페이지 유형
        if pdf_info and page_num < len(pdf_info):
            page_type = pdf_info[page_num]["type"]
        else:
            page_type = "?"
        
        row = f"{page_num:>4} | {page_num+1:>3} | {page_type:>4}"
        
        for label in labels:
            text, chunk_count = get_page_text(results[label], page_num)
            good, total, rate = calc_recognition_rate(text)
            summary[label]["good"] += good
            summary[label]["total"] += total
            
            rate_str = f"{rate:.1f}%" if total > 0 else "N/A"
            row += f" | {chunk_count:>8} | {good:>5}/{total:<5} | {rate_str:>10}"
        
        lines.append(row)
    
    # 전체 요약
    lines.append("-" * len(header))
    total_row = f"{'합계':>4} | {'':>3} | {'':>4}"
    for label in labels:
        s = summary[label]
        rate = (s["good"] / s["total"] * 100) if s["total"] > 0 else 0
        total_row += f" | {'':>8} | {s['good']:>5}/{s['total']:<5} | {rate:.1f}%".ljust(12)
    lines.append(total_row)
    
    # 문제 페이지 상세
    lines.append("")
    lines.append("=" * 80)
    lines.append("문제 페이지 상세 (인식률 < 80%)")
    lines.append("=" * 80)
    
    for page_num in range(max_page + 1):
        for label in labels:
            text, chunk_count = get_page_text(results[label], page_num)
            good, total, rate = calc_recognition_rate(text)
            if total > 0 and rate < 80:
                lines.append(f"\n[{label}] Page {page_num} (PDF {page_num+1}p) - 인식률 {rate:.1f}%")
                halluc = count_hallucination_chars(text)
                zero = count_zero_hallucination(text)
                if halluc > 0:
                    # 반복된 단어 찾기
                    words = re.findall(r'(\S+)(?:\s*\|\s*\1){4,}', text)
                    lines.append(f"  반복 할루시네이션: {halluc}자, 반복 단어: {set(words)}")
                if zero > 0:
                    lines.append(f"  0 반복: {zero}자")
                lines.append(f"  텍스트 앞 200자: {text[:200]}")
    
    # 출력
    output = "\n".join(lines)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"\n결과 저장: {OUTPUT_FILE}", file=sys.stderr)
    print(output)

if __name__ == "__main__":
    main()
