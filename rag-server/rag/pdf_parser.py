from __future__ import annotations

import fitz
import sys
import re
import time
import logging
import os
from datetime import datetime

DEFAULT_PDF_PARSER = "fitz"

_last_done_reason = "stop"
_ocr_logger = None
_RUN_DIR = None

def parse_pdf_to_page_items(file_bytes: bytes, parser_name: str = DEFAULT_PDF_PARSER):
    global _ocr_logger, _RUN_DIR
    
    # 업로드 시점에 로그 폴더 생성
    _RUN_DIR = f"/data/logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(_RUN_DIR, exist_ok=True)

    _ocr_logger = logging.getLogger("ocr_pdf_parser")
    _ocr_logger.setLevel(logging.DEBUG)
    log_handler = logging.FileHandler(f"{_RUN_DIR}/ocr_process.log", encoding="utf-8")
    log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _ocr_logger.addHandler(log_handler)

    parser_key = (parser_name or DEFAULT_PDF_PARSER).strip().lower()

    # ── Bible 전용 파서 분기 ──────────────────────────────
    if parser_key == "bible":
        return _parse_with_bible_headings(file_bytes, ocr_engine=None)
    if parser_key == "bible_qwen_vl":
        return _parse_with_bible_headings(file_bytes, ocr_engine="qwen_vl")
    # ─────────────────────────────────────────────────────

    if parser_key == "fitz":
        raw_pages = _extract_with_fitz(file_bytes)
    elif parser_key == "fitz_qwen_vl":
        raw_pages = _extract_with_fitz_ocr(file_bytes, ocr_engine="qwen_vl")
    else:
        raise ValueError(f"Unsupported PDF parser: {parser_name}")

    page_items = []

    for raw_page in raw_pages:
        page_num = raw_page["page"]
        page_text = _clean_pdf_text(raw_page.get("text", ""))

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
                "metadata": {
                    "parser": parser_key,
                    **raw_meta,
                },
            }
        )

    return page_items


# ══════════════════════════════════════════════════════════════
# Bible 전용: fitz get_text("dict") 로 헤딩 감지
# ══════════════════════════════════════════════════════════════
 
# 폰트 크기 기준 (이 PDF 전용)
#   H1 : size >= 16      예) 창세기, 출애굽기, 성경 역사
#   H2 : 10 <= size < 16 예) 서론, 내용 개요, 주석
#   H3 : size ≈ 8.3, font=YDVYGO145  예) 창세기와 역사, 1:1-2:3 ...
# 제외 (header/footer)
#   size <= 7.0, font=YDVYGO135  → 러닝 헤드
#   size ≈ 8.5, font=ITCGaramond → 페이지 번호
 
def _get_page_headings_and_body(page_obj) -> list[dict]:
    """
    페이지 내 헤딩 위치 기준으로 섹션을 분리.
    반환: [{"h1": "", "h2": "", "h3": "", "text": "..."}, ...]
    """
    d = page_obj.get_text("dict")

    sections = []
    cur_h1 = cur_h2 = cur_h3 = ""
    body_parts = []

    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                size = span.get("size", 0)
                font = span.get("font", "")
                text = span.get("text", "").strip()
                if not text:
                    continue

                # 헤더/푸터 제외
                if size <= 7.0 and "YDVYGO135" in font:
                    continue
                if abs(size - 8.5) < 0.2 and "Garamond" in font:
                    continue

                # 헤딩 감지 → 이전 섹션 저장 후 새 섹션 시작
                is_heading = False
                if size >= 16.0:
                    if body_parts:
                        sections.append({"h1": cur_h1, "h2": cur_h2, "h3": cur_h3,
                                         "text": " ".join(body_parts).strip()})
                        body_parts = []
                    cur_h1, cur_h2, cur_h3 = text, "", ""
                    is_heading = True
                elif size >= 10.0:
                    if body_parts:
                        sections.append({"h1": cur_h1, "h2": cur_h2, "h3": cur_h3,
                                         "text": " ".join(body_parts).strip()})
                        body_parts = []
                    cur_h2, cur_h3 = text, ""
                    is_heading = True
                elif abs(size - 8.3) < 0.3 and "YDVYGO145" in font:
                    if body_parts:
                        sections.append({"h1": cur_h1, "h2": cur_h2, "h3": cur_h3,
                                         "text": " ".join(body_parts).strip()})
                        body_parts = []
                    cur_h3 = text
                    is_heading = True

                if not is_heading:
                    body_parts.append(text)

    # 마지막 섹션
    if body_parts:
        sections.append({"h1": cur_h1, "h2": cur_h2, "h3": cur_h3,
                         "text": " ".join(body_parts).strip()})

    return sections


def _parse_with_bible_headings(file_bytes: bytes, ocr_engine: str | None) -> list[dict]:
    """
    fitz get_text("dict") 로 헤딩을 감지하고 본문을 추출.
    ocr_engine="qwen_vl" 이면 이미지 페이지는 기존 OCR 로직 적용.
    반환 형식: parse_pdf_to_page_items 와 동일 + h1/h2/h3 키 포함.
    """
    page_items = []
    cur_h1 = cur_h2 = cur_h3 = ""
 
    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_obj:
        for page_index, page_obj in enumerate(pdf_obj):
            page_start = time.time()
 
            # 1) 헤딩 + 본문 분리
            sections = _get_page_headings_and_body(page_obj)

            # OCR은 페이지 단위 1회 수행
            ocr_text = ""
            page_type = "text"
            if ocr_engine == "qwen_vl":
                images = page_obj.get_images(full=True)
                if len(images) >= 50:
                    page_type = "org_chart"
                    print(
                        f"  [SKIP] page={page_index+1} 조직도 감지 → OCR 스킵",
                        file=sys.stderr, flush=True,
                    )
                elif len(images) > 0:
                    page_type = "image"
                    global _last_done_reason
                    _last_done_reason = "stop"
                    ocr_text = _ocr_with_split(page_obj, ocr_engine)

            for sec_idx, section in enumerate(sections):
                new_h1 = section["h1"]
                new_h2 = section["h2"]
                new_h3 = section["h3"]
                body_text = section["text"]

                # 헤딩 갱신
                if new_h1 and new_h1 != cur_h1:
                    cur_h1, cur_h2, cur_h3 = new_h1, new_h2, new_h3
                elif new_h2 and new_h2 != cur_h2:
                    cur_h2, cur_h3 = new_h2, new_h3
                elif new_h3 and new_h3 != cur_h3:
                    cur_h3 = new_h3

                # OCR 텍스트는 마지막 섹션에만 합침
                is_last = (sec_idx == len(sections) - 1)
                if is_last and ocr_text:
                    merged = _clean_pdf_text((body_text + "\n" + ocr_text).strip())
                else:
                    merged = _clean_pdf_text(body_text)

                page_elapsed = time.time() - page_start

                if not merged:
                    continue

                # 한글 비율 필터 (OCR 모드 제외)
                if ocr_engine is None:
                    ko_count = sum(1 for ch in merged if "가" <= ch <= "힣")
                    ko_ratio = ko_count / max(len(merged), 1)
                    if ko_ratio < 0.10 and len(merged) > 50:
                        print(
                            f"[filter][page={page_index+1}] skipped: ko_ratio={ko_ratio:.1%}",
                            file=sys.stderr, flush=True,
                        )
                        continue

                msg = (
                    f"[bible][page={page_index+1}] "
                    f"h1={cur_h1!r} h2={cur_h2!r} h3={cur_h3!r} "
                    f"body_len={len(merged)} elapsed={page_elapsed:.2f}s"
                )
                print(msg, file=sys.stderr, flush=True)
                _ocr_logger.info(msg)

                page_items.append({
                    "page":     page_index,
                    "text":     merged,
                    "h1":       cur_h1,
                    "h2":       cur_h2,
                    "h3":       cur_h3,
                    "metadata": {
                        "parser":    f"bible_{ocr_engine or 'fitz'}",
                        "page_type": page_type,
                        "elapsed":   page_elapsed,
                    },
                })

 
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
    if re.search(r'(\S+)(\s*\|\s*\1){4,}', t):
        return True
    # 빈 파이프 반복 (유니코드 파이프 포함)
    if re.search(r'([\|│\u2502]\s*){4,}', t):
        return True
    # 고유 글자 수 대비 총 길이 - 같은 문자가 과도하게 반복
    unique_chars = len(set(t))
    if len(t) > 60 and unique_chars < 15:
        return True
    # 텍스트 후반부 품질 체크 - 뒤쪽 절반의 의미 비율
    half = t[len(t)//2:]
    meaningful_half = sum(1 for c in half if c.isalnum() or '가' <= c <= '힣')
    if len(half) > 30 and meaningful_half / max(len(half), 1) < 0.08:
        return True
    # 전체 의미 비율
    meaningful = sum(1 for c in t if c.isalnum() or '가' <= c <= '힣')
    if meaningful / max(len(t), 1) < 0.15:
        return True
    return False


def _ocr_with_split(page_obj, ocr_engine, rect=None, depth=0):
    """done_reason=length면 재귀적으로 분할 OCR (최대 4분할)"""
    global _last_done_reason
    if depth > 2:  # 최대 8분할
        r = rect or page_obj.rect
        pix = page_obj.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False, clip=r)
        result = _run_ocr(pix.tobytes("png"), ocr_engine, model="qwen2.5vl:7b")
        if _last_done_reason == 'length':
            return ""  # 여기서도 length면 포기
        if not result.replace('|','').replace('-','').replace(' ','').replace('\n','').strip():
            return ""
        return result

    r = rect or page_obj.rect
    pix = page_obj.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False, clip=r)
    text = _run_ocr(pix.tobytes("png"), ocr_engine, model="qwen2.5vl:7b")

    if _last_done_reason == "length":
        print(f"  [SPLIT] depth={depth} done_reason=length → 분할 재시도", file=sys.stderr, flush=True)
        mid_y = (r.y0 + r.y1) / 2
        top = fitz.Rect(r.x0, r.y0, r.x1, mid_y)
        bot = fitz.Rect(r.x0, mid_y, r.x1, r.y1)
        text = (
            _ocr_with_split(page_obj, ocr_engine, top, depth+1) + "\n" +
            _ocr_with_split(page_obj, ocr_engine, bot, depth+1)
        ).strip()

    return text


def _extract_with_fitz_ocr(file_bytes: bytes, ocr_engine: str):
    raw_pages = []
    with fitz.open(stream=file_bytes, filetype="pdf") as pdf_obj:
        for page_index, page_obj in enumerate(pdf_obj):
            page_start = time.time()
            base_text = _clean_pdf_text(page_obj.get_text() or "")

            # 이미지 면적 비율 계산
            images = page_obj.get_images(full=True)
            has_images = len(images) > 0
            
            # 페이지 유형 분류
            if len(images) >= 50 and len(base_text) < 200:
                page_type = "org_chart"  # 조직도/다이어그램 → OCR 스킵
            elif len(images) > 0 and len(base_text) < 1000:
                page_type = "image"      # 표 이미지 → OCR
            else:
                page_type = "text"       # 텍스트 → 직접 추출

            do_ocr = (page_type == "image")
            if page_type == "org_chart":
                print(f"  [SKIP] page={page_index+1} 조직도/다이어그램 감지 (images={len(images)}) → OCR 스킵", file=sys.stderr, flush=True)

            ocr_text = ""
            if do_ocr:
                if ocr_engine == "qwen_vl":
                    # 큰 이미지 일 경우 이미지를 분할해서 OCR 
                    global _last_done_reason
                    _last_done_reason = "stop"
                    ocr_text = _ocr_with_split(page_obj, ocr_engine)

            merged = _clean_pdf_text((base_text + "\n" + ocr_text).strip()) if do_ocr else base_text

            page_elapsed = time.time() - page_start

            # 페이지별 실시간 로그
            msg = (
                f"[qwen_vl][page={page_index+1}] "
                f"do_ocr={do_ocr} base_len={len(base_text)} "
                f"ocr_len={len(ocr_text)} merged_len={len(merged)}"
            )
            print(msg, file=sys.stderr, flush=True)
            _ocr_logger.info(msg)
            if do_ocr and ocr_text:
                detail = f"  OCR결과(앞200자): {ocr_text[:200]}"
                print(detail, file=sys.stderr, flush=True)
                _ocr_logger.info(detail)

            raw_pages.append({
                "page": page_index,
                "text": merged,
                "metadata": {
                    "page_type": page_type,
                    "has_images": has_images,
                    "elapsed": page_elapsed,
                    "ocr_used": do_ocr,
                    "ocr_engine": ocr_engine if do_ocr else None,
                    "base_text_len": len(base_text),
                    "ocr_text_len": len(ocr_text),
                },
            })
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


def _run_ocr(image_bytes: bytes, engine: str, **kwargs) -> str:
    global _last_done_reason
    engine_key = (engine or "").strip().lower()

    if engine_key == "qwen_vl":
        import base64, requests

        model_name = kwargs.get("model", "qwen2.5vl:72b")
        b64 = base64.b64encode(image_bytes).decode()
    
        # 모델별 ollama 서버 주소
        ollama_url = "http://host.docker.internal:11436/api/chat"

        ocr_options = {
            "temperature": 0.0,
            "num_predict": 8192,
            # "repeat_penalty": 1.5,    # 72b 모델 주석
            # "num_ctx": 8192   # 72b 모델 주석
        }
        
        base_prompt = """Output in TSV format only. No markdown. No | character. No --- lines.

- 표는 탭(\t)으로 열을 구분하고 줄바꿈으로 행을 구분
- 이미지에 있는 열 구조 그대로 출력 (열 추가/삭제 금지)
- 빈 셀은 빈 탭으로 유지
- 표 외 텍스트(제목, 주석 등)도 그대로 출력
- 영문 대문자와 숫자 혼동 주의: G↔6, O↔0, I↔1
- 인식할 텍스트가 없으면 빈 줄만 출력하고 종료
"""

        messages = []
        messages.append({
            "role": "user",
            "images": [b64],
            "content": base_prompt
        })

        try:
            resp = requests.post(ollama_url, json={
                "model": model_name,
                "messages": messages,
                "stream": False,
                "options": ocr_options
            }, timeout=300)
        except requests.exceptions.ReadTimeout:
            print(f"  [TIMEOUT] OCR timeout → 분할 재시도", file=sys.stderr, flush=True)
            _last_done_reason = 'length'
            return ""

        result = resp.json()
        # ollama 오류 응답 처리
        if "error" in result:
            print(f"  [OLLAMA_ERROR] {result['error']}", file=sys.stderr, flush=True)
            return ""
        if "message" not in result:
            print(f"  [OLLAMA_ERROR] 응답에 message 없음: {result}", file=sys.stderr, flush=True)
            return ""
        raw_content = result["message"]["content"]
        content = raw_content.strip()
        
        # 디버그: 항상 출력
        print(
            f"  [DEBUG_RESP] model={model_name} "
            f"raw_len={len(raw_content)} stripped_len={len(content)} "
            f"eval_count={result.get('eval_count', '?')} "
            f"done_reason={result.get('done_reason', '?')} "
            f"raw[:300]={repr(raw_content[:300])}",
            file=sys.stderr, flush=True,
        )

        done = result.get('done_reason', '')
        semesters = re.findall(r'(\d+)학기', content)
        max_semester = max((int(n) for n in semesters), default=0)
        if not done and (
            content.replace('|', '').replace('-', '').replace('\n', '').strip() == ''
            or max_semester > 12
        ):
            _last_done_reason = 'length'
        else:
            _last_done_reason = done if done else 'stop'
        return content


    raise ValueError(f"Unsupported OCR engine: {engine}")
