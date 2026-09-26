import copy
import hashlib
import json

import pytest
import yaml

from sdd.design_contracts import audit, enforce
from sdd.evidence import fingerprint
from sdd.export_site import export_site
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator


@pytest.fixture
def contract(tmp_cfg):
    text = 'void Device::stop() { cancelPending(); }'
    sha = hashlib.sha256(text.encode()).hexdigest()
    source = dict(id='stop', file='device.cpp', start='void Device::stop()', end='}', sha256=sha)
    topic = dict(id='shutdown', title='종료 계약', question='대기 요청은 어떻게 반환됩니까?', sources=[source],
                 statements=[dict(text='stop()은 대기 요청을 취소합니다.', evidence=['stop'], covers=['lifetime'])])
    section = dict(id='device', title='장치 설계', output='device.md', kind='prose',
                   design_requirements=[dict(id='lifetime', question='대기 요청의 수명은 어떻게 끝납니까?')],
                   design_topics=[topic], show_evidence=True, next=dict(title='장치 설계', link='device.md'))
    model = KnowledgeModel(meta={'source_commit': 'a' * 40}, evidence={
        'device/shutdown/stop': dict(selector=copy.deepcopy(source), commit='a' * 40, file='device.cpp',
                                     line=10, end_line=10, sha256=sha, text=text, status='available')})
    def save():
        tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
        model.save(tmp_cfg.facts_path)
    save()
    return section, model, save


def test_contract_renders_answers_coverage_and_original_source_without_llm(tmp_cfg, contract):
    section, model, _ = contract
    class NoModel:
        def chat(self, *a, **kw):
            pytest.fail('Source-bound answers must not be rewritten by an LLM')
    paths = Generator(tmp_cfg, model, NoModel()).run()
    text = paths[0].read_text(encoding='utf-8')
    assert 'stop()은 대기 요청을 취소합니다. `device.cpp:10`' in text
    assert '| 대기 요청의 수명은 어떻게 끝납니까? | [종료 계약](#종료-계약)' in text
    assert 'void Device::stop() { cancelPending(); }' in text
    assert 'generation_method: source-bound-contract' in text
    report = json.loads((tmp_cfg.build_dir / 'design-review.json').read_text(encoding='utf-8'))
    assert report['sections']['device']['requirements'][0]['status'] == 'documented'
    assert report['sections']['device']['human_review'] == 'pending'
    export_site(tmp_cfg)


@pytest.mark.parametrize('mutation, expected', [
    ('remove_topic', '답변이 없습니다'), ('empty_answer', '비어 있는'),
    ('only_limitation', 'limited'), ('unknown_requirement', '정의되지 않은'),
    ('unmapped_answer', 'covers'), ('changed_pin', '지문'),
    ('changed_text', '발췌 본문'), ('duplicate_topic', '중복'),
    ('duplicate_source', '중복'), ('missing_source', '근거'),
    ('llm_answer', '설계 설명이 없습니다'), ('invalid_kind', 'kind'),
])
def test_incomplete_contract_cannot_pass(tmp_cfg, contract, mutation, expected):
    section, model, save = contract
    topic = section['design_topics'][0]
    st = topic['statements'][0]
    if mutation == 'remove_topic':
        section['design_topics'] = []
    elif mutation == 'empty_answer':
        st['text'] = ' '
    elif mutation == 'only_limitation':
        st['kind'] = 'limitation'
    elif mutation == 'unknown_requirement':
        st['covers'] = ['missing']
    elif mutation == 'unmapped_answer':
        del st['covers']
    elif mutation == 'changed_pin':
        topic['sources'][0]['sha256'] = 'changed'
    elif mutation == 'changed_text':
        model.evidence['device/shutdown/stop']['text'] = 'unrelated code'
    elif mutation == 'duplicate_topic':
        section['design_topics'].append(copy.deepcopy(topic))
    elif mutation == 'duplicate_source':
        topic['sources'].append(copy.deepcopy(topic['sources'][0]))
    elif mutation == 'missing_source':
        model.evidence.clear()
    elif mutation == 'llm_answer':
        del topic['statements']
    elif mutation == 'invalid_kind':
        st['kind'] = 'invented'
    assert audit(model, section)['status'] == 'incomplete'
    with pytest.raises(ValueError, match=expected):
        enforce(model, section)
    save()
    with pytest.raises(ValueError, match=expected):
        Generator(tmp_cfg, model, None).run()
    assert not (tmp_cfg.sdd_dir / 'device.md').exists()


def test_preflight_preserves_all_manuscripts_on_failure(tmp_cfg, contract):
    section, model, save = contract
    Generator(tmp_cfg, model, None).run()
    original = (tmp_cfg.sdd_dir / 'device.md').read_bytes()
    section['design_requirements'].append(dict(id='errors', question='오류는 어떻게 처리합니까?'))
    save()
    # Even an earlier, independently valid page must not be overwritten.
    early = dict(id='early', title='먼저 생성할 문서', kind='prose', narration='facts', facts={'classes': []})
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [early, section]}), encoding='utf-8')
    with pytest.raises(ValueError, match='errors'):
        Generator(tmp_cfg, model, None).run()
    assert (tmp_cfg.sdd_dir / 'device.md').read_bytes() == original
    assert not (tmp_cfg.sdd_dir / 'early.md').exists()


def test_export_blocks_missing_answer_even_if_input_fingerprint_matches(tmp_cfg, contract):
    section, model, save = contract
    Generator(tmp_cfg, model, None).run()
    export_site(tmp_cfg)
    before = (tmp_cfg.build_dir / 'site' / 'site-manifest.json').read_bytes()
    section['design_topics'][0]['statements'][0]['kind'] = 'limitation'
    save()
    path = tmp_cfg.sdd_dir / 'device.md'
    text = path.read_text(encoding='utf-8')
    import re
    text = re.sub(r'evidence_fingerprint: .*', 'evidence_fingerprint: ' + fingerprint(model, section), text)
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError, match='limited'):
        export_site(tmp_cfg)
    assert (tmp_cfg.build_dir / 'site' / 'site-manifest.json').read_bytes() == before


def test_limitation_is_visible_but_does_not_replace_answer(tmp_cfg, contract):
    section, model, save = contract
    section['design_topics'][0]['statements'].append(dict(
        text='드라이버의 완료 시점은 기기에서 확인해야 합니다.', kind='limitation', evidence=['stop'], covers=['lifetime']))
    save()
    item = enforce(model, section)['requirements'][0]
    assert item['status'] == 'documented' and item['limitations'] == ['shutdown']
    path = Generator(tmp_cfg, model, None).run()[0]
    assert '실행 확인 항목: 드라이버' in path.read_text(encoding='utf-8')


def test_changed_requirements_invalidate_carryover(tmp_cfg, contract):
    from sdd.carryover import carry_forward
    section, model, save = contract
    path = Generator(tmp_cfg, model, None).run()[0]
    section['design_requirements'].append(dict(id='state', question='허용 상태는 무엇입니까?'))
    model.meta['source_commit'] = 'b' * 40
    model.evidence['device/shutdown/stop']['commit'] = 'b' * 40
    save()
    promoted, stale = carry_forward(tmp_cfg, model, [])
    assert not promoted and stale[0][0] == path
    assert 'source_commit: ' + 'a' * 40 in path.read_text(encoding='utf-8')


@pytest.mark.parametrize('field', ['covers', 'evidence'])
def test_malformed_contract_lists_report_configuration_error(contract, field):
    section, model, _ = contract
    section['design_topics'][0]['statements'][0][field] = 'not-a-list'
    with pytest.raises(ValueError, match='문자열 목록'):
        enforce(model, section)


@pytest.mark.parametrize('field,value', [('file', None), ('start', 123), ('end', '')])
def test_invalid_source_selector_fails_before_collection(tmp_cfg, contract, monkeypatch, field, value):
    from sdd.evidence import collect

    section, model, save = contract
    section['design_topics'][0]['sources'][0][field] = value
    save()
    before = copy.deepcopy(model.evidence)
    before_disk = tmp_cfg.facts_path.read_bytes()
    monkeypatch.setattr('sdd.evidence.subprocess.run', lambda *a, **kw: pytest.fail('Invalid selectors must fail before Git reads'))
    with pytest.raises(ValueError, match=field):
        collect(tmp_cfg, model)
    assert model.evidence == before
    assert tmp_cfg.facts_path.read_bytes() == before_disk
    with pytest.raises(ValueError, match=field):
        enforce(model, section)


@pytest.mark.parametrize('mixed', [False, True])
def test_topic_generation_takes_precedence_over_facts_narration(tmp_cfg, contract, mixed, monkeypatch):
    from sdd.export_html import _split
    from sdd.validate import Verdict

    section, model, save = contract
    section.pop('design_requirements')  # Optional topics can use model-authored prose.
    section['narration'] = 'facts'
    if mixed:
        other = copy.deepcopy(section['design_topics'][0])
        other['id'] = 'model-topic'
        section['design_topics'].append(other)
        model.evidence['device/model-topic/stop'] = copy.deepcopy(model.evidence['device/shutdown/stop'])
    del section['design_topics'][-1]['statements']
    save()
    tmp_cfg.agent.kind = 'ollama'
    generator = Generator(tmp_cfg, model, None)
    calls = []
    def ask(*args):
        calls.append(args[0])
        return '모델이 소스 발췌를 설명합니다. `device.cpp:10`', [], Verdict(ok=True)
    monkeypatch.setattr(generator, '_ask', ask)
    meta, _ = _split(generator.run()[0].read_text(encoding='utf-8'))
    assert len(calls) == 1
    assert meta['generation_method'] == ('mixed' if mixed else 'facts-and-llm')
    assert meta['agent'].startswith('ollama/')
