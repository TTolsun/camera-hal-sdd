from pathlib import Path

import pytest

from sdd.export_site import export_site
from sdd.diagrams import class_diagram
from sdd.facts.model import ClassInfo, Relation


def prepare(cfg, model):
    model.meta['source_commit'] = 'a' * 40
    model.save(cfg.facts_path)
    cfg.sections_file.write_text('''sections:
  - id: device
    output: device.md
    title: Device
    kind: prose
    facts:
      classes: [CameraDevice]
    next: {title: Details, link: nested/detail.md}
  - id: nested
    output: nested/detail.md
    title: Details
    kind: prose
    facts:
      classes: [PipeThread]
    next: {title: Device, link: device.md}
''', encoding='utf-8')
    cfg.raw['site'] = {'title': 'Test <Site>', 'source_url': 'https://github.com/example/source'}
    cfg.raw['diagrams'] = {'enabled': True}
    cfg.sdd_dir.mkdir(parents=True)
    (cfg.sdd_dir / 'nested').mkdir()
    text = '---\nsource_commit: ' + 'a' * 40 + '\nstatus: needs-review\n---\n\n'
    (cfg.sdd_dir / 'device.md').write_text(text + '# Device\n\n## Evidence\n\n'
        '`device/CameraDevice.h:40`\n\n`invented.h:99`\n\n[Details](nested/detail.md#methods)\n\n## 한글 목차\n\n[이동](#한글-목차)\n', encoding='utf-8')
    (cfg.sdd_dir / 'nested/detail.md').write_text(text + '# Details\n\n## Methods\n\n'
        '[Device](../device.md#evidence)\n', encoding='utf-8')


def test_site_preserves_verdicts_and_links_nested_pages(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    originals = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*.md')}
    out = export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    nested = (out / 'nested/detail.html').read_text(encoding='utf-8')
    assert 'href="nested/detail.html#methods"' in doc
    assert 'href="../device.html#evidence"' in nested
    assert 'href="../assets/reading.css"' in nested
    assert 'Test &lt;Site&gt;' in doc
    assert 'id="한글-목차"' in doc and 'href="#한글-목차"' in doc
    assert '사람 검토 전' in doc and 'needs-review' in doc
    assert 'https://github.com/example/source/blob/' + 'a' * 40 + '/device/CameraDevice.h#L40' in doc
    assert '<code>invented.h:99</code>' in doc
    assert '/invented.h#L99' not in doc
    assert (out / 'device.mmd').exists()
    assert 'nested/detail.html#methods' in (out / 'assets/search.json').read_text(encoding='utf-8')
    assert all(p.read_bytes() == original for p, original in originals.items())
    assert (out / 'device.md').read_bytes() == originals[tmp_cfg.sdd_dir / 'device.md']


def test_stale_facts_abort_before_publication(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    sample_model.meta['source_commit'] = 'b' * 40
    sample_model.save(tmp_cfg.facts_path)
    with pytest.raises(RuntimeError, match='commits differ'):
        export_site(tmp_cfg)
    assert not (tmp_cfg.build_dir / 'site').exists()


def test_changed_design_configuration_blocks_same_commit_publication(tmp_cfg, sample_model):
    import yaml
    from sdd.generate import Generator
    from sdd.llm import Agent
    prepare(tmp_cfg, sample_model)
    sections = tmp_cfg.sections()
    sections[0]['semantic_review'] = True
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    site = export_site(tmp_cfg)
    manifest = (site / 'site-manifest.json').read_bytes()
    sections[0]['answers'] = ['Changed design question']
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='Design evidence changed'):
        export_site(tmp_cfg)
    assert (site / 'site-manifest.json').read_bytes() == manifest
    # Removing the option must not bypass the existing page's fingerprint.
    sections[0].pop('semantic_review')
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='Design evidence changed'):
        export_site(tmp_cfg)


def test_diagram_has_only_extracted_relations_and_unique_node_ids(sample_model):
    sample_model.classes['other::PipeThread'] = ClassInfo('other::PipeThread')
    sample_model.relations += [Relation('PipeThread', 'CameraDevice', 'association')]
    diagram = class_diagram(sample_model, ['*PipeThread'])
    assert 'other::PipeThread' in diagram
    assert diagram.count('["PipeThread"]') == 1
    assert '상속' in diagram and 'Thread' in diagram
    assert 'CameraDevice' not in diagram  # Unselected association target is not invented/expanded.
    with pytest.raises(RuntimeError, match='narrow facts.classes'):
        class_diagram(sample_model, ['*'], limit=1)
    assert diagram == class_diagram(sample_model, ['*PipeThread'])


def test_rejects_output_path_traversal(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    tmp_cfg.sections_file.write_text('sections:\n  - output: ../escape.md\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='Invalid documentation path'):
        export_site(tmp_cfg)


def test_repeated_builds_update_relationships_without_duplicate_diagrams(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.site_build import verify_site
    prepare(tmp_cfg, sample_model)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    markdown = (tmp_cfg.sdd_dir / 'nested/detail.md').read_text(encoding='utf-8')
    assert markdown.count('```mermaid') == 1
    out = export_site(tmp_cfg)
    first = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    export_site(tmp_cfg)
    assert first == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    assert (out / 'nested/detail.html').read_text(encoding='utf-8').count('class="mermaid"') == 1
    sample_model.classes['PipeThread'].bases = ['NewThreadBase']
    sample_model.save(tmp_cfg.facts_path)
    export_site(tmp_cfg)
    diagram = (out / 'nested/detail.mmd').read_text(encoding='utf-8')
    assert 'NewThreadBase' in diagram and '["Thread"]' not in diagram
    assert verify_site(out)['html_pages'] == 3


def test_removed_sections_clean_owned_artifacts_and_keep_unrelated_files(tmp_cfg, sample_model):
    import yaml
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    (out / 'CNAME').write_text('docs.example.org', encoding='utf-8')
    sections = yaml.safe_load(tmp_cfg.sections_file.read_text(encoding='utf-8'))
    sections['sections'] = sections['sections'][:1]
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections), encoding='utf-8')
    page = tmp_cfg.sdd_dir / 'device.md'
    page.write_text(page.read_text(encoding='utf-8').replace('[Details](nested/detail.md#methods)', ''), encoding='utf-8')
    export_site(tmp_cfg)
    assert not (out / 'nested/detail.html').exists()
    assert not (out / 'nested/detail.mmd').exists()
    assert (out / 'CNAME').read_text() == 'docs.example.org'
    assert (tmp_cfg.sdd_dir / 'nested/detail.md').exists()


def test_failed_build_preserves_previous_site(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    tmp_cfg.raw['diagrams']['max_nodes'] = 1
    with pytest.raises(RuntimeError, match='narrow facts.classes'):
        export_site(tmp_cfg)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}


def test_edited_artifact_is_not_silently_overwritten(tmp_cfg, sample_model):
    from sdd.site_build import verify_site
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    page = out / 'device.html'
    page.write_text('manual edit', encoding='utf-8')
    with pytest.raises(RuntimeError, match='manually changed'):
        export_site(tmp_cfg)
    with pytest.raises(RuntimeError, match='Artifact changed'):
        verify_site(out)
    assert page.read_text() == 'manual edit'


def test_generate_command_automatically_builds_configured_site(tmp_cfg, sample_model):
    import yaml
    from sdd.cli import main
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['enabled'] = True
    config = tmp_cfg.root / 'sdd.yaml'
    config.write_text(yaml.safe_dump(tmp_cfg.raw), encoding='utf-8')
    assert main(['--config', str(config), 'generate']) == 0
    assert (tmp_cfg.build_dir / 'site/site-manifest.json').is_file()
    assert '```mermaid' in (tmp_cfg.sdd_dir / 'device.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('collision', ['nested/detail.html', 'nested'])
def test_unmanaged_output_collision_preserves_entire_destination(tmp_cfg, sample_model, collision):
    prepare(tmp_cfg, sample_model)
    out = tmp_cfg.build_dir / 'site'
    target = out / collision
    target.parent.mkdir(parents=True)
    target.write_text('operator-owned content', encoding='utf-8')
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match='Unmanaged artifact|not a directory'):
        export_site(tmp_cfg)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}


@pytest.mark.parametrize('policy', [{'enabled': False}, {'enabled': True, 'classes': ['NoSuchClass']}])
def test_rebuild_removes_stale_managed_diagram_but_preserves_manual_mermaid(tmp_cfg, sample_model, policy):
    import yaml
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.site_build import verify_site
    prepare(tmp_cfg, sample_model)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    page = tmp_cfg.sdd_dir / 'device.md'
    page.write_text(page.read_text(encoding='utf-8') + '\n```mermaid\nflowchart LR\n  ManualA --> ManualB\n```\n', encoding='utf-8')
    original = page.read_bytes()
    out = export_site(tmp_cfg)
    assert (out / 'device.mmd').exists()
    sections = yaml.safe_load(tmp_cfg.sections_file.read_text(encoding='utf-8'))
    section = sections['sections'][0]
    section['diagram'] = {'enabled': policy['enabled']}
    if 'classes' in policy:
        section['facts']['classes'] = policy['classes']
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections), encoding='utf-8')
    export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    assert doc.count('class="mermaid"') == 1
    assert 'ManualA' in doc
    assert not (out / 'device.mmd').exists()
    assert page.read_bytes() == original
    assert verify_site(out)['broken_links'] == 0


def test_existing_generation_without_diagram_opt_in_accepts_large_models(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.llm import Agent
    for i in range(20):
        name = f'ExtraClass{i}'
        sample_model.classes[name] = ClassInfo(name)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run(['overview'])
    assert '<!-- sdd:class-diagram -->' not in (tmp_cfg.sdd_dir / 'overview.md').read_text(encoding='utf-8')
