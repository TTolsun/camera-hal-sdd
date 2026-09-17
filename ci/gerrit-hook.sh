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
#   DOCS_DIR           docs 프로젝트의 로컬 clone (여기에 sdd/ 를 복사해서 commit 한다)
#   DOCS_REMOTE        (예: ssh://gerrit.internal:29418/camera/hal-docs)
#   MANUAL_PAGES       docs 저장소에서 사람이 관리해 덮어쓰면 안 되는 페이지 (기본: index.md constraints.md decisions.md)

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

# 생성된 sdd/ 를 docs 저장소(별도 Gerrit 프로젝트의 로컬 clone, DOCS_DIR)에 복사해서 change 로 올린다.
# 이 저장소(파이프라인 코드)의 HEAD 를 그대로 push 하지 않는다. docs 프로젝트에는 문서만 들어간다.
# Change-Id 는 docs clone 에 설치된 commit-msg 훅이 붙인다.
if [[ -n "${DOCS_DIR:-}" && -n "${DOCS_REMOTE:-}" ]]; then
  # 사람이 쓰는 페이지(sections.yaml 의 kind: manual 과 index.md)는 docs 저장소가 원본이다.
  # 파이프라인 결과로 덮어쓰지 않도록 복사 전에 보관했다가 되돌린다.
  MANUAL_PAGES="${MANUAL_PAGES:-index.md constraints.md decisions.md}"
  KEEP="$(mktemp -d)"
  for page in $MANUAL_PAGES; do
    [[ -f "$DOCS_DIR/sdd/$page" ]] && cp "$DOCS_DIR/sdd/$page" "$KEEP/$page"
  done
  rm -rf "$DOCS_DIR/sdd"
  cp -r sdd "$DOCS_DIR/sdd"
  for page in $MANUAL_PAGES; do
    [[ -f "$KEEP/$page" ]] && cp "$KEEP/$page" "$DOCS_DIR/sdd/$page"
  done
  rm -rf "$KEEP"
  cd "$DOCS_DIR"
  git add sdd
  if ! git diff --cached --quiet; then
    SUMMARY="$(head -c 4000 "$HERE/build/change_impact.md" 2>/dev/null || echo '(변경 요약 없음)')"
    git commit -q -m "docs: SDD 갱신 (HAL change ${GERRIT_CHANGE_NUMBER:-?} / ${REVISION:0:10})" \
                  -m "$SUMMARY"
    git push -q "$DOCS_REMOTE" "HEAD:refs/for/${BRANCH}%topic=hal-${GERRIT_CHANGE_NUMBER:-manual}"
  fi
fi
