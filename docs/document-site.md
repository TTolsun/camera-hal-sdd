# 설계 문서 사이트 구성

**문서 생성과 디자인 기술은 `camera-hal-sdd`에서 관리하고, 출력만 문서 저장소에 배포합니다.**

`sdd export-site`는 기존 Markdown과 facts를 읽어 여러 페이지로 구성된 정적 사이트를 만듭니다. LLM을 다시 호출하지 않으며 원본 Markdown, 자동 인용 검사 결과, 생성 시각을 변경하지 않습니다. 현재 생성기는 사람의 승인 기록을 관리하지 않으므로 사이트에도 사람 검토 전으로 표시합니다.

유지보수 기준은 [DESIGN.md](../DESIGN.md)입니다. 그림 생성은 `src/sdd/diagrams.py`, 페이지 배치는 `src/sdd/export_site.py`, 출력 검증·관리는 `src/sdd/site_build.py`, 공통 화면 자산은 `src/sdd/site_assets/`에서 관리합니다. 변경을 생성기에 반영하면 다음 빌드부터 모든 페이지에 적용됩니다.

## 반복 실행 계약

libcamera 설정은 `site.enabled: true`이므로 `sdd generate`와 `sdd run`이 문서와 Mermaid 원문을 만든 뒤 사이트 빌드·검증까지 이어서 수행합니다. 다른 프로젝트도 같은 옵션으로 연결합니다.

```powershell
# 현재 facts에서 문장과 Mermaid를 다시 생성하고 사이트까지 만듭니다.
uv run sdd --config examples/libcamera/sdd.yaml generate
# 문장은 유지하고 그림·화면·검색 목록만 최신 facts와 공통 규칙으로 다시 만듭니다.
uv run sdd --config examples/libcamera/sdd.yaml export-site
uv run sdd --config examples/libcamera/sdd.yaml verify-site
```

`site-manifest.json`에는 입력 facts·Markdown·섹션 설정과 생성 코드·출력 파일의 SHA-256을 남깁니다. 같은 입력으로 사이트를 두 번 만들면 같은 결과와 build ID가 나옵니다. 문장을 새로 생성하는 LLM 호출 자체의 결정성을 뜻하지 않습니다.

빌드는 먼저 임시 위치에서 내부 링크를 확인합니다. 검증 실패 시 기존 사이트에 반영하지 않습니다. 다음 빌드에서 사라진 페이지·그림은 직전 manifest에 기록된 생성 파일만 정리합니다. 사람이 수정한 생성 파일은 덮어쓰지 않고 오류를 냅니다. 원고나 공통 테마에서 수정한 뒤 다시 생성하세요.

새 출력 경로에 manifest가 관리하지 않는 파일이 이미 있거나, 필요한 디렉터리 자리에 파일이 있으면 반영 전에 중단합니다. 기존 사이트를 처음 가져올 때에도 해당 파일을 별도로 보존하고 빈 출력 디렉터리에서 빌드하세요.

설계 근거 검사가 활성화된 페이지의 이월에는 인용뿐 아니라 선택한 구조·주제·발췌의 지문도 같아야 합니다. 근거가 달라지면 재생성이 필요합니다. [설계 근거 검사](design-evidence.md)의 자동 검사 통과는 사람의 의미 검토나 실행 검증을 뜻하지 않습니다.

사이트는 현재 facts와 원고의 커밋이 같아야 합니다. 새 커밋에서 일부 원고만 갱신해 나머지 원고가 이전 커밋에 남으면 게시를 중단합니다. `generate --from-impact`는 영향이 없던 원고의 `파일:줄` 인용을 새 facts로 재검증한 뒤 통과한 원고의 `source_commit`을 이월하므로(`carryover.py`, frontmatter에 `revalidated_from` 기록), 통상적인 증분 실행에서는 전체 재생성 없이 기준이 맞습니다. 인용이 어긋난 원고는 이월하지 않고 재생성 대상으로 보고하며, 그때는 해당 섹션을 다시 생성해야 게시할 수 있습니다.

Git push는 생성 명령에 포함하지 않습니다. 검증된 출력 디렉터리를 `libcamera-sdd/docs`로 지정해 만들고 해당 저장소에서 커밋·push하면 기존 Pages가 게시합니다. 생성기 CI는 push/PR마다 Windows·Linux, Python 3.11·3.14에서 회귀 검사를 실행하도록 구성했습니다. 원격 CI 통과 여부는 실제 실행 결과로 확인해야 합니다.

## 디자인 기준

[libcamera 공식 문서](https://docs.libcamera.org/master/)의 좌측 탐색 메뉴·중앙 본문·우측 목차를 참고했습니다. OMM 저장소의 `DESIGN.md`, `docs/design.md`, `assets/reading.css`, `templates/jekyll/_layouts/default.html`에서 읽기 중심 배치와 다이어그램 상호작용 규칙을 적용했습니다. 참고한 로컬 OMM 기준 커밋은 `12a704c603136308b87b26c4081bd6102d42395e`입니다.

별도의 Mermaid 이름을 가진 `SKILL.md`는 해당 저장소에서 찾지 못했습니다. 실제로 적용한 것은 위 디자인 문서와 템플릿의 규칙입니다. OMM 실행기를 설치하거나 OMM 저장소를 수정하지 않았습니다.

본문 너비는 최대 720px이며 글자 크기는 16px, 줄 간격은 1.8입니다. 흰 배경에 짙은 녹색을 제한적으로 사용합니다. 좁은 화면에서는 메뉴를 접고 목차를 본문 위에 표시합니다. 외부 글꼴은 내려받지 않습니다.

검색은 실제 문서 제목과 모든 페이지의 절 제목을 대상으로 합니다. Ctrl/⌘+K로 열고 Escape로 닫습니다. 표와 코드 블록은 가로로 스크롤할 수 있습니다. 이전·다음 링크는 실제 문서 순서에서 생성합니다.

## 실행 방법

```powershell
uv run sdd --config examples/libcamera/sdd.yaml export-site
python -m http.server 8765 --bind 127.0.0.1 --directory examples/libcamera/build/site
```

브라우저에서 `http://127.0.0.1:8765/`를 엽니다. 검색과 Mermaid 모듈을 불러오려면 파일을 직접 여는 대신 HTTP 서버를 사용하세요.

설정은 `sdd.yaml`의 `site`에 둡니다.

```yaml
site:
  enabled: true
  title: libcamera 설계 문서
  intro: site-intro.md
  source_url: https://github.com/TTolsun/libcamera-sdd
```

`intro`는 설정 파일 기준의 안내 원고입니다. 생략하면 짧은 기본 안내를 만듭니다. 페이지는 `sections.yaml` 순서를 따르며 추가 MkDocs·시나리오 페이지를 뒤에 연결합니다. `source_url`은 선택 사항이며 GitHub/GHE의 `/blob/<commit>/<file>#L<line>` 주소 형식을 사용합니다. 해당 커밋이 실제로 존재하는 미러를 지정하세요.

인용 링크는 facts에 기록된 정확한 파일·줄과 40자리 커밋이 일치할 때만 생성합니다. 원고와 facts의 커밋이 다르면 prose 페이지의 새 그림 생성을 거절합니다.

```powershell
uv run sdd --config examples/libcamera/sdd.yaml export-site --out build/publication/libcamera-sdd/docs
```

이 명령은 출력만 갱신하며 Git push를 수행하지 않습니다. 출력 디렉터리를 전용으로 사용하세요. 기존 `export-html`은 단일 파일 배포용으로 유지합니다.

## Mermaid 구성

prose 페이지에서 선택한 클래스와 직접 기반 클래스를 facts로부터 도식화합니다. 실제 추출한 상속과 필드 참조를 사용하며 이름만으로 호출 순서를 추측하지 않습니다. 표시할 노드가 한도를 넘으면 빌드가 실패하므로 섹션을 나누거나 명시적으로 한도를 조정하세요. 기존 Mermaid 코드 블록도 렌더링합니다.

자동 클래스 그림은 `diagrams.enabled: true` 또는 섹션의 `diagram.enabled: true`로 켭니다. 기본값은 꺼짐이며, 기존 프로젝트의 넓은 클래스 선택 범위 때문에 문서 생성이 실패하지 않도록 합니다. libcamera 예제는 명시적으로 켜져 있습니다. 그림을 끄거나 선택한 클래스가 없어지면 사이트 재빌드에서 이전 자동 그림과 `.mmd`를 제거합니다. 원고의 이동 링크를 유지하기 위해 해당 절 제목과 안내 문장은 남기며, 직접 작성한 Mermaid 블록은 보존합니다.

```yaml
diagrams:
  enabled: true
  max_nodes: 16
  direction: LR
  strip_namespace: 'libcamera::'
```

각 섹션의 `diagram`에 같은 키를 넣으면 해당 섹션만 재정의합니다. 지원 방향은 LR·TB·RL·BT입니다. 네임스페이스 생략은 표시 이름에만 적용하며 노드 식별에는 전체 이름을 사용합니다.

그림을 누르거나 키보드 Enter/Space를 누르면 확대 창이 열립니다. 요소 이름 검색, 실제 SVG 크기 변경, 화면에 맞춤, 100% 복귀를 지원합니다. Escape로 닫으면 원래 그림과 키보드 초점을 복원합니다. `.mmd` 원문도 내려받을 수 있습니다.

Mermaid는 OMM 템플릿과 같은 `11.12.0` 버전에 고정했고 `securityLevel: strict`로 실행합니다. CDN을 읽지 못하면 실패 안내와 원문을 표시합니다. 사내에서는 해당 버전의 전체 ESM 배포 디렉터리와 의존 chunk를 함께 호스팅한 뒤 경로를 지정하세요.

```powershell
uv run sdd --config examples/libcamera/sdd.yaml export-site --mermaid assets/vendor/mermaid/mermaid.esm.min.mjs
```

위 경로는 생성 사이트 루트 기준입니다. 명령은 Mermaid 패키지를 다운로드하지 않으므로 사내 자산 배포 절차에서 파일들을 준비해야 합니다.

## OMM 이력 관리 도입 여부

현재는 Git 원본 이력, facts의 `source_commit`, 문서의 생성 메타데이터, `impact`의 기준·대상 커밋으로 분석 입력과 영향을 추적합니다. OMM의 commit 수집도 Git 이력과 검토 체크포인트를 기반으로 하므로 지금 추가하면 이력 상태를 이중으로 관리하게 됩니다.

따라서 이번에는 디자인 규칙만 적용합니다. 향후 여러 저장소의 설계 의도·제약·검토 승인과 체크포인트를 공통 OMM 항목으로 연결해야 할 때 도입을 다시 판단합니다. 현재 커밋 감시·자동 갱신·검토 승인 파이프라인이 완성되었다는 뜻은 아닙니다.

다음 단계: 게시 문서의 근거와 문장을 검토합니다.
