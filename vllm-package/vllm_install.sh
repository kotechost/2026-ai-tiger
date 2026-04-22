#!/usr/bin/env bash
# vLLM + transformers (EXAONE fork) 클린 재설치 스크립트
#
# 전제:
#   - /home/solihost/vllm-package/vllm-exaone        (git clone 완료)
#   - /home/solihost/vllm-package/transformers-exaone (git clone 완료)
#
# 동작:
#   1) 실행 중인 vllm 종료
#   2) 기존 venv 제거 후 /home/solihost/vllm-package/uv-vllm 에 새로 생성
#   3) vllm-exaone  -> 111bd61ac... 커밋으로 고정 후 빌드 설치
#   4) transformers -> a6cb457f...  커밋으로 고정 후 --no-deps 로 덮어쓰기
#   5) run_vllm.sh 의 VENV 경로를 새 위치로 교체
#   6) 설치 검증 출력
#
# 사용법:
#   bash /home/solihost/vllm-package/vllm_install.sh

set -euo pipefail

# ---- 설정 -----------------------------------------------------------------
PKG_DIR="/home/solihost/vllm-package"
VENV_DIR="$PKG_DIR/uv-vllm"
PY_VER="3.12"

VLLM_SRC="$PKG_DIR/vllm-exaone"
VLLM_REPO="https://github.com/lkm2835/vllm.git"
VLLM_BRANCH="add-exaone4_5"
VLLM_COMMIT="111bd61ac966a57eb56c562ab02349de6c600d38"

TF_SRC="$PKG_DIR/transformers-exaone"
TF_REPO="https://github.com/nuxlear/transformers.git"
TF_BRANCH="add-exaone4_5"
TF_COMMIT="31991e758f53bebaed91a066ed9ceb476a3c7777"

RUN_SCRIPT="$PKG_DIR/run_vllm.sh"
STOP_SCRIPT="$PKG_DIR/stop_vllm.sh"

# ---- 유틸 -----------------------------------------------------------------
log()  { printf "\n\033[1;32m[%(%H:%M:%S)T] %s\033[0m\n" -1 "$*"; }
warn() { printf "\n\033[1;33m[%(%H:%M:%S)T] %s\033[0m\n" -1 "$*"; }
die()  { printf "\n\033[1;31m[%(%H:%M:%S)T] %s\033[0m\n" -1 "$*" >&2; exit 1; }

# ---- 사전 점검 -------------------------------------------------------------
command -v uv  >/dev/null 2>&1 || die "uv 가 설치되어 있지 않습니다. (https://docs.astral.sh/uv/)"
command -v git >/dev/null 2>&1 || die "git 이 설치되어 있지 않습니다."

# 소스 폴더가 없으면 clone
ensure_repo() {
    local dir="$1" repo="$2" branch="$3"
    if [ -d "$dir/.git" ]; then
        log "repo 존재: $dir"
    else
        log "clone: $repo -> $dir (branch: $branch)"
        rm -rf "$dir"
        git clone --branch "$branch" "$repo" "$dir"
    fi
}

ensure_repo "$VLLM_SRC" "$VLLM_REPO" "$VLLM_BRANCH"
ensure_repo "$TF_SRC"   "$TF_REPO"   "$TF_BRANCH"

# ---- 1) 실행 중인 vllm 종료 -------------------------------------------------
log "1) 실행 중인 vllm 종료"
[ -x "$STOP_SCRIPT" ] && "$STOP_SCRIPT" || true
pkill -f "vllm serve" 2>/dev/null || true

# ---- 2) venv 재생성 --------------------------------------------------------
log "2) 기존 venv 제거 후 새로 생성: $VENV_DIR"
rm -rf "$VENV_DIR"

uv venv "$VENV_DIR" --python "$PY_VER"

# venv 활성화 (현재 쉘 세션에서)
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "python: $(python -V) @ $(which python)"

# torch / torchvision / torchaudio (CUDA 13.0 빌드)
log "torch / torchvision / torchaudio 설치 (cu130)"
uv pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu130

# --no-build-isolation 으로 빌드하려면 venv 안에 빌드 의존성이 전부 있어야 함.
# vllm-exaone/requirements/build.txt 에 정확한 목록이 있음
# (setuptools, setuptools-scm, cmake, ninja, packaging, wheel, jinja2 ...)
log "빌드 의존성 설치 (requirements/build.txt)"
uv pip install --no-cache-dir -r "$VLLM_SRC/requirements/build.txt"

# ---- 3) vLLM 빌드 ---------------------------------------------------------
log "3) vLLM 로컬 소스 빌드  ($VLLM_COMMIT)"
cd "$VLLM_SRC"

git fetch origin --tags
git checkout "$VLLM_BRANCH"
git checkout "$VLLM_COMMIT"
log "vllm HEAD: $(git log -1 --oneline)"

rm -rf build/ dist/ ./*.egg-info

# 현재 venv 의 torch/CUDA 재사용 (격리 빌드 금지). 15~20분 소요.
uv pip install --no-cache-dir --no-build-isolation .

# ---- 4) transformers 덮어쓰기 ---------------------------------------------
log "4) transformers 덮어쓰기 ($TF_COMMIT)"
cd "$TF_SRC"

git fetch origin --tags
git checkout "$TF_BRANCH"
git checkout "$TF_COMMIT"
log "transformers HEAD: $(git log -1 --oneline)"

rm -rf build/ dist/ ./*.egg-info

uv pip uninstall transformers -y || true
uv pip install --no-cache-dir --no-deps .

# transformers(v5.3.0.dev0) 가 요구하는 huggingface-hub 로 업그레이드
# (vllm 이 미리 깔아둔 0.36.x 에는 is_offline_mode 등이 없어 import 실패)
log "huggingface-hub 업그레이드 (>=1.5.0,<2.0)"
uv pip install --no-cache-dir "huggingface-hub>=1.5.0,<2.0"

# ---- 5) run_vllm.sh 의 VENV 경로 갱신 --------------------------------------
if [ -f "$RUN_SCRIPT" ]; then
    log "5) $RUN_SCRIPT 의 VENV 경로 갱신"
    if grep -q '^VENV=' "$RUN_SCRIPT"; then
        sed -i "s|^VENV=.*|VENV=$VENV_DIR|" "$RUN_SCRIPT"
        grep '^VENV=' "$RUN_SCRIPT"
    else
        warn "run_vllm.sh 에 VENV= 라인이 없어 건너뜀"
    fi
else
    warn "run_vllm.sh 가 없어 경로 갱신 스킵"
fi

# ---- 6) 검증 --------------------------------------------------------------
log "6) 설치 검증"
python - <<'PY'
import pathlib
import vllm, transformers
print(f"vllm         : {vllm.__version__}  @ {pathlib.Path(vllm.__file__).resolve()}")
print(f"transformers : {transformers.__version__}  @ {pathlib.Path(transformers.__file__).resolve()}")
PY

echo
echo "vllm src HEAD         : $(git -C "$VLLM_SRC" rev-parse HEAD)"
echo "transformers src HEAD : $(git -C "$TF_SRC" rev-parse HEAD)"

log "완료. 서버 실행: $RUN_SCRIPT"
