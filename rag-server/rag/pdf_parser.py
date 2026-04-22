from __future__ import annotations

from io import BytesIO

import fitz
import sys
import cv2
import numpy as np
from rag.ocr_postprocess import corrector
import re


# 학과명 자동 감지: 직전에 감지된 학과를 이후 페이지에 상속
def _detect_department_from_pages(raw_pages):
    """
    페이지 텍스트를 순서대로 스캔하며 학과명을 감지.
    감지된 학과명은 다음 학과가 나타날 때까지 이후 페이지에 상속.
    """
    current_dept = ""
    current_college = ""

    for page in raw_pages:
        text = page.get("text", "")[:500]  # 상단 500자만 스캔

        # 대학명 감지: "OO대학" (단독 라인 또는 페이지 상단)
        college_match = re.search(r"([가-힣]+대학)\s*$", text, re.MULTILINE)
        if college_match:
            candidate = college_match.group(1)
            # "대학교"는 제외, "OO대학"만 (의과대학, IT공학대학 등)
            if "대학교" not in candidate:
                current_college = candidate

        # 학과명 감지: "OO학과" 또는 "OO과" + 구분자/영문/줄바꿈
        dept_match = re.search(
            r"([가-힣A-Za-z]+(?:학과|공학과|학부))\s*[\|│\nD]",
            text[:300]
        )
        if not dept_match:
            dept_match = re.search(
                r"([가-힣]+과)\s+Department",
                text[:300]
            )
        if dept_match:
            current_dept = dept_match.group(1)

        # metadata에 추가
        if "metadata" not in page:
            page["metadata"] = {}
        page["metadata"]["department"] = current_dept
        page["metadata"]["college"] = current_college

    return raw_pages


DEFAULT_PDF_PARSER = "fitz"
_PADDLE_OCR = None


def parse_pdf_to_page_items(file_bytes: bytes, parser_name: str = DEFAULT_PDF_PARSER):
    parser_key = (parser_name or DEFAULT_PDF_PARSER).strip().lower()

    if parser_key == "fitz":
        raw_pages = _extract_with_fitz(file_bytes)
    elif parser_key == "fitz_pytesseract":
        raw_pages = _extract_with_fitz_ocr(file_bytes, ocr_engine="pytesseract")
    elif parser_key == "fitz_easyocr":
        raw_pages = _extract_with_fitz_ocr(file_bytes, ocr_engine="easyocr")
    elif parser_key == "fitz_rapidocr":
        raw_pages = _extract_with_fitz_ocr(file_bytes, ocr_engine="rapidocr")
    elif parser_key == "fitz_ppstructure":
        raw_pages = _extract_with_fitz_ppstructure(file_bytes)
    elif parser_key == "fitz_paddleocr":
        raw_pages = _extract_with_fitz_ocr(file_bytes, ocr_engine="paddleocr")
    elif parser_key == "fitz_hybrid":
        raw_pages = _extract_with_fitz_hybrid(file_bytes)
    elif parser_key == "fitz_qwen_vl":
        raw_pages = _extract_with_fitz_ocr(file_bytes, ocr_engine="qwen_vl")
    elif parser_key == "pdfplumber":
        raw_pages = _extract_with_pdfplumber(file_bytes)
    elif parser_key == "unstructured":
        raw_pages = _extract_with_unstructured(file_bytes)
    else:
        raise ValueError(f"Unsupported PDF parser: {parser_name}")
    
    # 학과 메타데이터 자동 감지
    raw_pages = _detect_department_from_pages(raw_pages)

    page_items = []

    for raw_page in raw_pages:
        page_num = raw_page["page"]
        page_text = _clean_pdf_text(raw_page.get("text", ""))
        # 후처리 적용
        page_text, audits = corrector.correct(page_text)

        # 추가: 교정 로그
        if audits:
            print(
                f"[postprocess][page={page_num}] corrections={len(audits)}",
                file=sys.stderr, flush=True,
            )
            for a in audits:
                print(
                    f"  [{a['type']}] \"{a['from']}\" → \"{a['to']}\" (score={a['score']})",
                    file=sys.stderr, flush=True,
                )

        if not page_text:
            continue

        # OCR 쓰레기 텍스트 필터: 한글 비율이 10% 미만이면 스킵
        ko_count = sum(1 for ch in page_text if "가" <= ch <= "힣")
        ko_ratio = ko_count / max(len(page_text), 1)
        if ko_ratio < 0.10 and len(page_text) > 50 and parser_key != "fitz_qwen_vl":
            print(
                f"[filter][page={page_num}] skipped: ko_ratio={ko_ratio:.1%}, len={len(page_text)}",
                file=sys.stderr, flush=True,
            )
            continue

        raw_meta = raw_page.get("metadata", {})
        page_items.append(
            {
                "page": page_num,
                "text": page_text,
                "department": raw_meta.get("department", ""),
                "college": raw_meta.get("college", ""),
                "metadata": {
                    "parser": parser_key,
                    **raw_meta,
                    "ocr_correction_count": len(audits),
                },
            }
        )

    return page_items


def _extract_with_fitz(file_bytes: bytes):
    raw_pages = []

    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_obj:
        for page_index, page_obj in enumerate(pdf_obj):
            raw_pages.append(
                {
                    "page": page_index,
                    "text": page_obj.get_text(),
                }
            )

    return raw_pages

def _extract_single_page_with_fitz(fitz_obj, page_index: int):
    if page_index < 0 or page_index >= len(fitz_obj):
        return ""

    try:
        return fitz_obj[page_index].get_text() or ""
    except Exception as err:
        print(
            f"[fitz][fallback-fail] page={page_index}, reason={err}",
            file=sys.stderr,
            flush=True,
        )
        return ""
    
# 품질 기반 판단
def _is_bad_ocr(text):
    t = text.strip()
    # 디버그: 실제 값 확인
    pipe_match = bool(re.search(r'([\|│\u2502]\s*){10,}', t))
    unique_chars = len(set(t))
    half = t[len(t)//2:]
    meaningful_half = sum(1 for c in half if c.isalnum() or '가' <= c <= '힣')
    meaningful_all = sum(1 for c in t if c.isalnum() or '가' <= c <= '힣')
    print(
        f"  [DEBUG_BAD_OCR] len={len(t)} pipe_match={pipe_match} "
        f"unique={unique_chars} half_len={len(half)} "
        f"half_meaningful={meaningful_half}/{len(half)} "
        f"all_meaningful={meaningful_all}/{len(t)} "
        f"text[:80]={repr(t[:80])}",
        file=sys.stderr, flush=True,
    )

    if len(t) < 50:
        return True
    # 단어 반복 할루시네이션
    if re.search(r'(\S+)(\s*\|\s*\1){10,}', t):
        return True
    # 빈 파이프 반복 (유니코드 파이프 포함)
    if re.search(r'([\|│\u2502]\s*){10,}', t):
        return True
    # 고유 글자 수 대비 총 길이 - 같은 문자가 과도하게 반복
    unique_chars = len(set(t))
    if len(t) > 60 and unique_chars < 15:
        return True
    # 텍스트 후반부 품질 체크 - 뒤쪽 절반의 의미 비율
    half = t[len(t)//2:]
    meaningful_half = sum(1 for c in half if c.isalnum() or '가' <= c <= '힣')
    if len(half) > 20 and meaningful_half / max(len(half), 1) < 0.15:
        return True
    # 전체 의미 비율
    meaningful = sum(1 for c in t if c.isalnum() or '가' <= c <= '힣')
    if meaningful / max(len(t), 1) < 0.3:
        return True
    return False


def _extract_with_fitz_ocr(file_bytes: bytes, ocr_engine: str, min_text_len: int = 80):
    raw_pages = []
    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_obj:
        for page_index, page_obj in enumerate(pdf_obj):
            base_text = _clean_pdf_text(page_obj.get_text() or "")

            # 이미지 면적 비율 계산
            images = page_obj.get_images(full=True)
            has_images = len(images) > 0
            page_area = page_obj.rect.width * page_obj.rect.height
            img_area = 0
            for img in images:
                try:
                    bbox = page_obj.get_image_bbox(img[7])
                    img_area += bbox.get_area()
                except:
                    pass
            img_ratio = (img_area / page_area * 100) if page_area > 0 else 0

            # 변경 후: 이미지가 30% 이상이거나, 이미지가 있는데 텍스트가 짧으면 OCR
            do_ocr = img_ratio >= 30 or (len(images) > 0 and len(base_text) < 200)

            ocr_text = ""
            if do_ocr:
                if ocr_engine == "qwen_vl":
                    pix = page_obj.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
                    image_bytes = pix.tobytes("png")
                    
                    # 1차: qwen3-vl:8b
                    ocr_text = _run_ocr(image_bytes, ocr_engine, model="qwen3-vl:8b") # 전처리 없이 OCR
                    
                    # 반복 할루시네이션 감지
                    if _is_bad_ocr(ocr_text):
                        print(
                            f"  [FALLBACK] page={page_index+1} 8b 실패 → 7b로 재시도",
                            file=sys.stderr, flush=True,
                        )
                        # 2차: qwen2.5vl:7b 폴백
                        ocr_text = _run_ocr(image_bytes, ocr_engine, model="qwen2.5vl:7b") # 전처리 없이 OCR
                else:
                    pix = page_obj.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                    image_bytes = pix.tobytes("png")
                    ocr_text = _run_ocr_best(image_bytes, ocr_engine) # 전처리 OCR

            merged = _clean_pdf_text((base_text + "\n" + ocr_text).strip()) if do_ocr else base_text

            # 페이지별 실시간 로그
            print(
                f"[qwen_vl][page={page_index+1}] "
                f"do_ocr={do_ocr} base_len={len(base_text)} "
                f"ocr_len={len(ocr_text)} merged_len={len(merged)}",
                file=sys.stderr, flush=True,
            )
            if do_ocr and ocr_text:
                print(f"  OCR결과(앞200자): {ocr_text[:200]}", file=sys.stderr, flush=True)

            raw_pages.append({
                "page": page_index,
                "text": merged,
                "metadata": {
                    "has_images": has_images,
                    "ocr_used": do_ocr,
                    "ocr_engine": ocr_engine if do_ocr else None,
                    "base_text_len": len(base_text),
                    "ocr_text_len": len(ocr_text),
                },
            })
    return raw_pages

def _extract_with_fitz_ppstructure(file_bytes: bytes, min_text_len: int = 80):
    from paddleocr import PPStructure

    table_engine = PPStructure(show_log=False, layout=False, lang="en")
    raw_pages = []

    print(f"[pp2][start] min_text_len={min_text_len}", file=sys.stderr, flush=True)

    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_obj:
        for page_index, page_obj in enumerate(pdf_obj):
            base_text = _clean_pdf_text(page_obj.get_text() or "")
            has_images = len(page_obj.get_images(full=True)) > 0
            do_table_ocr = has_images and len(base_text) < min_text_len

            table_text = ""
            table_count = 0

            if do_table_ocr:
                try:
                    pix = page_obj.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    arr = np.frombuffer(pix.tobytes("png"), dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                    result = table_engine(img)
                    lines = []

                    for block in result:
                        if isinstance(block, dict) and block.get("type") == "table":
                            table_count += 1
                            html = (block.get("res") or {}).get("html", "")
                            if html:
                                lines.append(html)

                    table_text = "\n".join(lines).strip()

                except Exception as err:
                    print(
                        f"[pp2][error] page={page_index+1}, reason={err}",
                        file=sys.stderr,
                        flush=True,
                    )

            merged = _clean_pdf_text((base_text + "\n" + table_text).strip()) if do_table_ocr else base_text

            print(
                f"[pp2][page] page={page_index+1}, has_images={has_images}, "
                f"base_len={len(base_text)}, do_table_ocr={do_table_ocr}, "
                f"table_count={table_count}, table_len={len(table_text)}",
                file=sys.stderr,
                flush=True,
            )

            raw_pages.append(
                {
                    "page": page_index,
                    "text": merged,
                    "metadata": {
                        "has_images": has_images,
                        "table_ocr_used": do_table_ocr,
                        "table_count": table_count,
                        "base_text_len": len(base_text),
                        "table_text_len": len(table_text),
                        "parser_version": "ppstructure_v2",
                    },
                }
            )

    print(f"[pp2][done] pages={len(raw_pages)}", file=sys.stderr, flush=True)
    return raw_pages

def _extract_with_pdfplumber(file_bytes: bytes):
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is not installed. Install it before using parser_name='pdfplumber'."
        ) from exc

    raw_pages = []
    fallback_count = 0

    with pdfplumber.open(BytesIO(file_bytes)) as pdf_obj, fitz.open(
        stream=file_bytes, filetype="pdf"
    ) as fitz_obj:
        for page_index, page_obj in enumerate(pdf_obj.pages):
            try:
                page_text = page_obj.extract_text() or ""
            except Exception as err:
                fallback_count += 1
                print(
                    f"[pdfplumber][fallback] page={page_index}, reason={err}",
                    file=sys.stderr,
                    flush=True,
                )
                page_text = _extract_single_page_with_fitz(fitz_obj, page_index)

            raw_pages.append(
                {
                    "page": page_index,
                    "text": page_text,
                }
            )

    if fallback_count:
        print(
            f"[pdfplumber] fallback_count={fallback_count}",
            file=sys.stderr,
            flush=True,
        )

    return raw_pages


def _extract_with_unstructured(file_bytes: bytes):
    try:
        from unstructured.partition.pdf import partition_pdf
    except ImportError as exc:
        raise ImportError(
            "unstructured is not installed. Install it before using parser_name='unstructured'."
        ) from exc

    raw_pages_map = {}

    elements = partition_pdf(file=BytesIO(file_bytes))

    for element in elements:
        metadata = getattr(element, "metadata", None)
        page_number = getattr(metadata, "page_number", None)
        if page_number is None:
            page_index = 0
        else:
            page_index = max(int(page_number) - 1, 0)

        element_text = str(element).strip()
        if not element_text:
            continue

        raw_pages_map.setdefault(page_index, []).append(element_text)

    raw_pages = []

    for page_index in sorted(raw_pages_map):
        raw_pages.append(
            {
                "page": page_index,
                "text": "\n".join(raw_pages_map[page_index]),
            }
        )

    return raw_pages


def _clean_pdf_text(text: str):
    if not text:
        return ""

    lines = [line.rstrip() for line in text.splitlines()]
    cleaned_lines = []

    for line in lines:
        normalized = " ".join(line.split())
        if normalized:
            cleaned_lines.append(normalized)

    return "\n".join(cleaned_lines).strip()


# =========================================================
# OCR 전처리 유틸
# =========================================================

def _deskew_image(img):
    """
    이미지 기울기 보정.
    - OTSU 이진화 + 최소외접사각형 각도 기반으로 회전 보정
    - 좌표가 너무 적으면 원본 반환
    """

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(bw > 0))
    if len(coords) < 20:
        return img

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _preprocess_variants(image_bytes: bytes):
    """제너레이터: variant를 하나씩 생성하여 yield → 메모리 절약"""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return

    # 1) 기울기 보정
    img = _deskew_image(img)

    # 2) 그레이스케일
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3) 표 라인 제거 함수
    def remove_table_lines(gray_img):
        inv = cv2.bitwise_not(gray_img)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        h_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, h_kernel)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        v_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kernel)
        lines_mask = cv2.add(h_lines, v_lines)
        cleaned = cv2.subtract(inv, lines_mask)
        return cv2.bitwise_not(cleaned)

    # # Variant 0: 원본 컬러 (deskew만)
    # yield img

    # 표 라인 제거 + 디노이징 (이후 variant 공통 베이스)
    no_lines = remove_table_lines(gray)
    del gray  # 원본 그레이 해제
    denoise = cv2.fastNlMeansDenoising(no_lines, None, 3, 7, 21)
    del no_lines  # 해제

    # Variant 1: 표 라인 제거 + 디노이징만
    yield denoise

    # Variant 2: 표 라인 제거 + CLAHE + 이진화
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoise)
    del denoise
    v3 = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    del clahe  # 해제
    yield v3
    del v3

    # # Variant 3: 표 라인 제거 + Sharpen + 이진화
    # blur = cv2.GaussianBlur(denoise, (0, 0), 1.2)
    # sharp = cv2.addWeighted(denoise, 1.8, blur, -0.8, 0)
    # del blur  # 해제
    # v4 = cv2.adaptiveThreshold(
    #     sharp, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 9
    # )
    # del sharp, denoise  # 해제
    # yield v4
    # del v4


# =========================================================
# OCR 결과 품질 평가 / Best Variant 선택
# =========================================================

def _ocr_text_quality_score(text: str) -> float:
    """
    OCR 텍스트의 간단한 품질 점수.
    - 유효 문자(한글/영문/숫자) 비율
    - 텍스트 길이 보너스
    """
    t = (text or "").strip()
    if not t:
        return 0.0

    useful = sum(ch.isalnum() or ("가" <= ch <= "힣") for ch in t)
    ratio = useful / max(len(t), 1)
    return ratio + min(len(t) / 1200.0, 0.5)


def _run_ocr_best(image_bytes: bytes, engine: str) -> str:
    """
    전처리 후보별 OCR을 수행하고,
    품질 점수가 가장 높은 텍스트를 최종 반환.
    """

    best_text = ""
    best_score = -1.0

    for img in _preprocess_variants(image_bytes):
        ok, enc = cv2.imencode(".png", img)
        del img
        if not ok:
            continue

        text = _run_ocr(enc.tobytes(), engine)
        del enc
        score = _ocr_text_quality_score(text)

        if score > best_score:
            best_score = score
            best_text = text

    return (best_text or "").strip()


# =========================================================
# 빌드형 Hybrid: 페이지별 best OCR 선택
# =========================================================
def _hybrid_text_quality_score(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0

    total = max(len(t), 1)

    # 1) 유효 문자 비율
    useful = sum(ch.isalnum() or ("가" <= ch <= "힣") for ch in t)
    ratio = useful / total

    # 2) 한글 비율 보너스 — 한글 PDF이므로 한글이 많을수록 정상
    ko_count = sum(1 for ch in t if "가" <= ch <= "힣")
    ko_bonus = min(ko_count / total * 3.0, 1.5)

    # 3) 길이 보너스
    length_bonus = min(len(t) / 2000.0, 1.0)

    # 4) 줄 수 보너스
    lines = [l for l in t.splitlines() if l.strip()]
    line_bonus = min(len(lines) / 40.0, 0.5)

    # 5) 깨진 문자 감점
    garbage_chars = sum(1 for ch in t if ch in "�□■▪▫◆◇○●◎☆★")
    garbage_penalty = min(garbage_chars / total * 5.0, 1.0)

    # 6) 노이즈 문자 감점 — 표 라인 오인식 패턴
    noise_chars = sum(1 for ch in t if ch in "[]|{}()")
    noise_penalty = min(noise_chars / total * 3.0, 1.0)

    # 7) HTML 감점
    lower = t.lower()
    html_penalty = 0.6 if ("<html" in lower or "<td>" in lower) else 0.0

    return ratio + ko_bonus + length_bonus + line_bonus - garbage_penalty - noise_penalty - html_penalty


def _extract_with_fitz_hybrid(file_bytes: bytes):
    import time
    raw_pages = []

    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_obj:  # PDF 1회만 열기
        for page_index, page_obj in enumerate(pdf_obj):
            page_start = time.time()
            base_text = _clean_pdf_text(page_obj.get_text() or "")

            # 이미지 면적 비율 계산
            images = page_obj.get_images(full=True)
            page_area = page_obj.rect.width * page_obj.rect.height
            img_area = 0
            for img in images:
                try:
                    bbox = page_obj.get_image_bbox(img[7])
                    img_area += bbox.get_area()
                except:
                    pass
            img_ratio = (img_area / page_area * 100) if page_area > 0 else 0

            # 이미지가 페이지의 50% 이상이면 OCR 수행
            do_ocr = img_ratio >= 50

            if not do_ocr:
                raw_pages.append({"page": page_index, "text": base_text, "metadata": {}})
                continue

                        # 전처리 1회만 수행
            pix = page_obj.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), alpha=False)
            image_bytes = pix.tobytes("png")
            del pix  # pixmap 즉시 해제

            # 각 variant에 대해 두 엔진 모두 실행
            best_text = ""
            best_score = -1.0
            best_engine = ""
            best_variant_idx = -1

            for vi, img in enumerate(_preprocess_variants(image_bytes)):
                ok, enc = cv2.imencode(".png", img)
                del img  # variant 이미지 즉시 해제
                if not ok:
                    continue
                enc_bytes = enc.tobytes()
                del enc  # 인코딩 버퍼 해제

                for engine in ("pytesseract", "paddleocr"):
                    text = _run_ocr(enc_bytes, engine)
                    score = _hybrid_text_quality_score(text)
                    if score > best_score:
                        best_score = score
                        best_text = text
                        best_engine = engine
                        best_variant_idx = vi  # 0=원본(주석), 1=라인제거+디노이징, 2=라인제거+CLAHE, 3=라인제거+Sharpen(주석)

                del enc_bytes  # 해제

            del image_bytes  # 원본 PNG 해제

            print(
                f"[hybrid][page={page_index+1}] "
                f"selected={best_engine} score={best_score:.4f} "
                f"variant={best_variant_idx} "
                f"elapsed={time.time() - page_start:.1f}s",
                file=sys.stderr,
                flush=True,
            )

            raw_pages.append({
                "page": page_index,
                "text": best_text,
                "metadata": {
                    "hybrid_used": True,
                    "selected_engine": best_engine,
                    "best_score": round(best_score, 4),
                },
            })

    return raw_pages


def _get_paddleocr_engine():
    global _PADDLE_OCR
    if _PADDLE_OCR is None:
        from paddleocr import PaddleOCR
        _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="korean", show_log=False)
    return _PADDLE_OCR


def _run_ocr(image_bytes: bytes, engine: str, **kwargs) -> str:
    engine_key = (engine or "").strip().lower()

    if engine_key == "pytesseract":
        import pytesseract
        from PIL import Image
        from io import BytesIO

        image = Image.open(BytesIO(image_bytes))
        # 한국어+영어 예시
        text = pytesseract.image_to_string(image, lang="kor+eng", config="--psm 4 --oem 3")
        return (text or "").strip()

    if engine_key == "easyocr":
        import easyocr

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        reader = easyocr.Reader(["ko", "en"], gpu=False)
        results = reader.readtext(img, detail=0)
        return "\n".join([t for t in results if t]).strip()

    if engine_key == "rapidocr":
        from rapidocr_onnxruntime import RapidOCR

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        ocr = RapidOCR()
        # 버전에 따라 반환 형태가 달라질 수 있음
        result, _ = ocr(img)
        texts = []
        if result:
            for line in result:
                # 일반적으로 line[1]에 텍스트
                if len(line) > 1 and isinstance(line[1], str):
                    texts.append(line[1])
        return "\n".join(texts).strip()

    if engine_key == "paddleocr":

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        ocr = _get_paddleocr_engine()
        result = ocr.ocr(img, cls=True)

        texts = []
        if result and result[0]:
            for line in result[0]:
                # line: [box, (text, score)]
                if len(line) >= 2 and isinstance(line[1], (list, tuple)) and len(line[1]) >= 1:
                    text = line[1][0]
                    if text:
                        texts.append(text)

        return "\n".join(texts).strip()

    if engine_key == "qwen_vl":
        import base64, requests

        model_name = kwargs.get("model", "qwen3-vl:8b")
        b64 = base64.b64encode(image_bytes).decode()
    
        # 모델별 ollama 서버 주소
        if "qwen3" in model_name:
            ollama_url = "http://host.docker.internal:11435/api/chat"
        else:
            ollama_url = "http://host.docker.internal:11436/api/chat"
        
        resp = requests.post(ollama_url, json={
            "model": model_name,
            "messages": [{
                "role": "user",
                "images": [b64],
                "content": ("/no_think\n" if "qwen3" in model_name else "") + """이 이미지는 한국의 대학교 문서입니다.
이 이미지는 한국의 대학교 문서입니다.
모든 텍스트를 빠짐없이 추출하세요.

규칙:
1. 표의 모든 행과 열을 빠짐없이 추출
2. 각 셀의 한국어, 영어, 숫자를 정확히 읽기
3. 빈 셀은 공백으로 표시
4. 표는 | 구분자로 행 단위로 출력
5. 표 외의 텍스트도 모두 포함
6. 추가 설명 없이 내용만 출력"""
            }],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 8192 if "qwen3" in model_name else 4096,
                "repeat_penalty": 1.5 if "qwen3" in model_name else 1.2,
                "num_ctx": 8192
            }
        }, timeout=600)
        return resp.json()["message"]["content"].strip()

    raise ValueError(f"Unsupported OCR engine: {engine}")
