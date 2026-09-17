#!/usr/bin/env bash
# Gerrit patchset-created 훅 또는 Jenkins/GitLab CI job 에서 호출하는 예시.
#
# 전제:
#   - 이 저장소(camera-hal-sdd)와 HAL 소스(hal-camera)가 나란히 checkout 되어 있다.
#   - NDK, clang-uml, uv 가 PATH 에 있고, 사내 LLM 엔드포인트에 도달할 수 있다.
#   - docs 저장소는 sdd/ 디렉터리를 그대로 담는 별도 Gerrit 프로젝트다 (DOCS_REMOTE).
#
# 환경 변수 (Gerrit 훅이 넘겨주는 값에 맞춰 조정):
#   GERRIT_CHANGE_NUMBER, GERRIT_PATCHSET_REVISION, GERRIT_BRANCH
#   SDD_AGENT_API_KEY  (openai-compatible 게이트웨이를 쓸 때만)
#   DOCS_REMOTE        (예: ssh://gerrit.internal:29418/camera/hal-docs)

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
HAL_DIR="${HAL_DIR:-$HERE/../hal-camera}"
REVISION="${GERRIT_PATCHSET_REVISION:-HEAD}"
BRANCH="${GERRIT_BRANCH:-main}"

cd "$HAL_DIR"
git fetch -q origin "$REVISION" 2>/dev/null || true
git checkout -q "$REVISION"
BASE="$(git merge-base HEAD "origin/$BRANCH")"

cd "$HERE"
uv sync --frozen 2>/dev/null || uv sync
uv run sdd compdb
uv run sdd run --base "$BASE"

# 생성된 문서를 docs 저장소 change 로 올린다. Change-Id 는 commit-msg 훅이 붙인다.
if [[ -n "${DOCS_REMOTE:-}" ]]; then
  git add sdd
  if ! git diff --cached --quiet; then
    SUMMARY="$(head -c 4000 build/change_impact.md 2>/dev/null || echo '(변경 요약 없음)')"
    git commit -q -m "docs: SDD 갱신 (HAL change ${GERRIT_CHANGE_NUMBER:-?} / ${REVISION:0:10})" \
                  -m "$SUMMARY"
    git push -q "$DOCS_REMOTE" "HEAD:refs/for/${BRANCH}%topic=hal-${GERRIT_CHANGE_NUMBER:-manual}"
  fi
fi
