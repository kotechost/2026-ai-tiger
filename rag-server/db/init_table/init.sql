-- =========================================================
-- 스키마 생성
-- =========================================================
CREATE SCHEMA IF NOT EXISTS bible_service;

COMMENT ON SCHEMA bible_service IS '대한성서공회 성경 본문 크롤링 및 벡터화 관리 스키마';


-- =========================================================
-- 테이블명 : bible_book_info
-- 설명     :
--   - bibleInfo API 호출마다 대한성서공회 사이트에서
--     수집한 역본별 책·장·절 정보를 저장한다.
--   - 장(chapter) 단위로 1 row씩 적재된다.
--     예) 개역개정 창세기(50장) → 50 rows 삽입
-- =========================================================

-- DROP TABLE bible_service.bible_book_info;

CREATE TABLE IF NOT EXISTS bible_service.bible_book_info (
    info_id         BIGSERIAL       NOT NULL,
    crawl_no        INTEGER         NOT NULL,
    version_code    VARCHAR(30)     NOT NULL,
    version_name    VARCHAR(100)    NOT NULL,
    book_order      INTEGER         NOT NULL,
    book_name       VARCHAR(100)    NOT NULL,
    book_code       VARCHAR(30)     NOT NULL,
    chap            INTEGER         NOT NULL,
    chap_sec_cnt    INTEGER         NOT NULL,
    total_chap      INTEGER         NOT NULL,
    total_sec       INTEGER         NOT NULL,
    raw_json        JSONB           NOT NULL,
    use_yn          CHAR(1)         NOT NULL DEFAULT 'Y',
    first_reg_dt    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_reg_dt     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT bible_book_info_pkey PRIMARY KEY (info_id),
    CONSTRAINT uk_bible_book_info_01 UNIQUE (crawl_no, version_code, book_code, chap),
    CONSTRAINT ck_bible_book_info_01 CHECK (crawl_no > 0),
    CONSTRAINT ck_bible_book_info_02 CHECK (chap > 0),
    CONSTRAINT ck_bible_book_info_03 CHECK (chap_sec_cnt >= 0),
    CONSTRAINT ck_bible_book_info_04 CHECK (total_chap > 0),
    CONSTRAINT ck_bible_book_info_05 CHECK (total_sec >= 0),
    CONSTRAINT ck_bible_book_info_06 CHECK (use_yn IN ('Y', 'N'))
);

COMMENT ON TABLE  bible_service.bible_book_info              IS '대한성서공회 사이트에서 수집한 성경 역본별 책·장·절 정보 (장 단위 저장)';
COMMENT ON COLUMN bible_service.bible_book_info.info_id      IS 'PK (자동증가 시퀀스)';
COMMENT ON COLUMN bible_service.bible_book_info.crawl_no     IS '수집 차수 — bibleInfo API 호출마다 기존 MAX+1 증가';
COMMENT ON COLUMN bible_service.bible_book_info.version_code IS '역본 코드  예: GAE, SAENEW';
COMMENT ON COLUMN bible_service.bible_book_info.version_name IS '역본 이름  예: 개역개정, 새번역';
COMMENT ON COLUMN bible_service.bible_book_info.book_order   IS '사이트 표시 순번 (1~66)';
COMMENT ON COLUMN bible_service.bible_book_info.book_name    IS '책 이름    예: 창세기, 여호수아기';
COMMENT ON COLUMN bible_service.bible_book_info.book_code    IS 'book 파라미터 코드  예: gen, jos, 1sa';
COMMENT ON COLUMN bible_service.bible_book_info.chap         IS '장 번호    예: 1, 2 … 50';
COMMENT ON COLUMN bible_service.bible_book_info.chap_sec_cnt IS '해당 장의 절 수  예: 창세기 1장 → 31';
COMMENT ON COLUMN bible_service.bible_book_info.total_chap   IS '해당 책의 총 장수  예: 창세기 → 50';
COMMENT ON COLUMN bible_service.bible_book_info.total_sec    IS '해당 책의 총 절수 합산  예: 창세기 → 1533';
COMMENT ON COLUMN bible_service.bible_book_info.raw_json     IS '해당 책 전체 수집 JSON (book_order, name, book, total_chap, total_sec, chapters 배열 포함)';
COMMENT ON COLUMN bible_service.bible_book_info.use_yn       IS '사용 여부  Y=사용, N=미사용';
COMMENT ON COLUMN bible_service.bible_book_info.first_reg_dt IS '최초 등록 일시';
COMMENT ON COLUMN bible_service.bible_book_info.last_reg_dt  IS '최종 등록 또는 수정 일시';

CREATE INDEX IF NOT EXISTS ix_bible_book_info_01 ON bible_service.bible_book_info (crawl_no);
CREATE INDEX IF NOT EXISTS ix_bible_book_info_02 ON bible_service.bible_book_info (version_code, book_code, chap);


-- =========================================================
-- 테이블명 : bible_crawl_content
-- 설명     :
--   - 대한성서공회 사이트에서 크롤링한 성경 본문을 절 단위로 저장
--   - 절 1건을 벡터 1건으로 사용
--   - 크롤링 실행(last_crawl_group_no)마다 새 행으로 적재 → 히스토리 보존
--   - 마지막 크롤링 실행 정보와 벡터화 상태를 함께 관리
-- =========================================================

-- DROP TABLE bible_service.bible_crawl_content;

CREATE TABLE IF NOT EXISTS bible_service.bible_crawl_content (
    content_id              BIGSERIAL       NOT NULL,
    last_crawl_group_no     BIGINT          NOT NULL,
    last_crawl_page_seq_no  INTEGER         NOT NULL,
    version_code            VARCHAR(30)     NOT NULL,
    version_name            VARCHAR(100)    NOT NULL,
    book_code               VARCHAR(30)     NOT NULL,
    book_name               VARCHAR(100)    NOT NULL,
    chap                    INTEGER         NOT NULL,
    sec                     INTEGER         NOT NULL,
    title                   VARCHAR(500),
    small_title             VARCHAR(500),
    verse_text              TEXT            NOT NULL,
    d2_hide_content         TEXT,
    source_url              TEXT,
    vector_stts_cd          VARCHAR(20)     NOT NULL DEFAULT 'READY',
    vector_dt               TIMESTAMP,
    vector_error_msg        TEXT,
    use_yn                  CHAR(1)         NOT NULL DEFAULT 'Y',
    first_reg_dt            TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_reg_dt             TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT bible_crawl_content_pkey    PRIMARY KEY (content_id),
    CONSTRAINT uk_bible_crawl_content_01   UNIQUE (last_crawl_group_no, version_code, book_code, chap, sec),
    CONSTRAINT ck_bible_crawl_content_01   CHECK (last_crawl_group_no > 0),
    CONSTRAINT ck_bible_crawl_content_02   CHECK (last_crawl_page_seq_no > 0),
    CONSTRAINT ck_bible_crawl_content_03   CHECK (chap > 0),
    CONSTRAINT ck_bible_crawl_content_04   CHECK (sec > 0),
    CONSTRAINT ck_bible_crawl_content_05   CHECK (use_yn IN ('Y', 'N')),
    CONSTRAINT ck_bible_crawl_content_06   CHECK (vector_stts_cd IN ('READY', 'SUCCESS', 'FAIL'))
);

COMMENT ON TABLE  bible_service.bible_crawl_content                        IS '대한성서공회 사이트에서 크롤링한 성경 본문 절 단위 저장 및 벡터화 상태 관리 테이블';
COMMENT ON COLUMN bible_service.bible_crawl_content.content_id             IS '성경 본문 데이터 PK';
COMMENT ON COLUMN bible_service.bible_crawl_content.last_crawl_group_no    IS '해당 본문이 마지막으로 반영된 크롤링 실행 번호';
COMMENT ON COLUMN bible_service.bible_crawl_content.last_crawl_page_seq_no IS '해당 본문이 마지막으로 반영될 때의 페이지 처리 순서';
COMMENT ON COLUMN bible_service.bible_crawl_content.version_code           IS '역본 코드  예: GAE, SAENEW';
COMMENT ON COLUMN bible_service.bible_crawl_content.version_name           IS '역본명     예: 개역개정, 새번역';
COMMENT ON COLUMN bible_service.bible_crawl_content.book_code              IS '성경 책 코드  예: gen, jos, 1sa';
COMMENT ON COLUMN bible_service.bible_crawl_content.book_name              IS '성경 책 이름  예: 창세기, 여호수아';
COMMENT ON COLUMN bible_service.bible_crawl_content.chap                   IS '장 번호';
COMMENT ON COLUMN bible_service.bible_crawl_content.sec                    IS '절 번호';
COMMENT ON COLUMN bible_service.bible_crawl_content.title                  IS '본문 대표 제목  예: [창세기1:1]';
COMMENT ON COLUMN bible_service.bible_crawl_content.small_title            IS '본문 소제목     예: 천지 창조';
COMMENT ON COLUMN bible_service.bible_crawl_content.verse_text             IS '절 본문 내용';
COMMENT ON COLUMN bible_service.bible_crawl_content.d2_hide_content        IS '사이트 팝업 각주 숨김 내용 (class=D2, display:none) — 미제공 절 안내, 사본 설명 등';
COMMENT ON COLUMN bible_service.bible_crawl_content.source_url             IS '크롤링 대상 원본 URL';
COMMENT ON COLUMN bible_service.bible_crawl_content.vector_stts_cd        IS '벡터화 상태 코드  READY / SUCCESS / FAIL';
COMMENT ON COLUMN bible_service.bible_crawl_content.vector_dt              IS '벡터화 완료 일시';
COMMENT ON COLUMN bible_service.bible_crawl_content.vector_error_msg       IS '벡터화 실패 시 오류 메시지';
COMMENT ON COLUMN bible_service.bible_crawl_content.use_yn                 IS '사용 여부  Y=사용, N=미사용';
COMMENT ON COLUMN bible_service.bible_crawl_content.first_reg_dt           IS '최초 등록 일시';
COMMENT ON COLUMN bible_service.bible_crawl_content.last_reg_dt            IS '최종 등록 또는 수정 일시';

-- 마지막 크롤링 실행 기준 조회용
CREATE INDEX IF NOT EXISTS ix_bible_crawl_content_01
    ON bible_service.bible_crawl_content (last_crawl_group_no, last_crawl_page_seq_no);

-- 본문 위치 조회용
CREATE INDEX IF NOT EXISTS ix_bible_crawl_content_02
    ON bible_service.bible_crawl_content (version_code, book_code, chap, sec);

-- 벡터화 대상 조회용
CREATE INDEX IF NOT EXISTS ix_bible_crawl_content_03
    ON bible_service.bible_crawl_content (vector_stts_cd, use_yn);
