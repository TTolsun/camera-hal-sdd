"""Revalidate design generation using preserved A/B facts and immutable source Git objects.

Does not rebuild libcamera or publish. Use a fresh --out to preserve failed runs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

from sdd.config import load
from sdd.diagrams import section_diagram
from sdd.facts.model import KnowledgeModel
from sdd.semantic import review
from sdd.site_build import verify_site


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error('Use a fresh --out; prior evidence must not be overwritten')
    cfg = load(Path(__file__).with_name('sdd.yaml'))
    models = {s: KnowledgeModel.load(args.baseline / s / 'facts.json') for s in ('a', 'b')}
    for side in models:
        if models[side].meta.get('comments', {}).get('errors') != 0:
            parser.error(f'{side}: baseline must have verified zero parse errors')
        for name in ('execution.json', 'facts-verification.json'):
            if not json.loads((args.baseline / side / name).read_text(encoding='utf-8'))['ok']:
                parser.error(f'{side}: failed baseline {name}')
    out.mkdir(parents=True)
    def command(run, *argv, expected=0):
        with (run / (argv[0] + '.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, '-m', 'sdd.cli', '--config', str(run / 'sdd.yaml'), *argv],
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode != expected:
            raise RuntimeError(f'{run.name}/{argv[0]} exit {result.returncode}; expected {expected}')
        return result.returncode
    for side, model in models.items():
        run = out / side
        run.mkdir()
        model.save(run / 'facts.json')
        raw = copy.deepcopy(cfg.raw)
        raw['paths'] = {k: str(v) for k, v in cfg.paths.items()}
        raw['source']['root'] = str(args.source.resolve())
        raw['output'] = {'facts_dir': '.', 'sdd_dir': 'sdd', 'diagrams_dir': 'sdd/diagrams'}
        raw['agent']['temperature'] = 0
        raw['site'].update(enabled=True, intro='intro.md')
        (run / 'intro.md').write_text('# libcamera 설계 검증\n\n공개 테스트 입력이며 사람 검토 전입니다.\n', encoding='utf-8')
        (run / 'sdd.yaml').write_text(yaml.safe_dump(raw, allow_unicode=True), encoding='utf-8')
    print('Generating A from preserved facts', flush=True)
    command(out / 'a', 'generate')
    print('Computing A/B impact with current document scope', flush=True)
    strict = command(out / 'b', 'impact', '--base', models['a'].meta['source_commit'],
                     '--head', models['b'].meta['source_commit'], '--base-facts', str(out / 'a/facts.json'),
                     '--fail-on-coverage-gap', expected=2)
    shutil.copytree(out / 'a/sdd', out / 'b/sdd')
    print('Generating B incrementally; unresolved scope findings remain visible', flush=True)
    command(out / 'b', 'generate', '--from-impact')
    result = {'base': models['a'].meta['source_commit'], 'head': models['b'].meta['source_commit'],
              'input_mode': 'reuse previously built and extracted facts; collect new pinned source excerpts',
              'strict_exit_code': strict, 'human_review': 'pending', 'runs': {}}
    diagrams = {}
    for side in models:
        run = out / side
        current = load(run / 'sdd.yaml')
        model = KnowledgeModel.load(run / 'facts.json')
        section = next(s for s in current.sections() if s['id'] == 'ipu3-lsc')
        diagrams[side] = section_diagram(current, model, section)
        (out / f'{side}.mmd').write_text(diagrams[side] + '\n', encoding='utf-8')
        manifest = run / 'build/site/site-manifest.json'
        before = manifest.read_bytes()
        command(run, 'export-site')
        assert before == manifest.read_bytes(), 'Repeat site build must be identical'
        verify_site(run / 'build/site')
        report = json.loads((run / 'build/content-review.json').read_text(encoding='utf-8'))
        old = (args.baseline / side / 'sdd/ipu3-lsc-probe.md').read_text(encoding='utf-8')
        prose = old.split('## 구조 설명\n\n', 1)[1].split('<!-- sdd:class-diagram -->')[0]
        golden_findings = review(prose, model, model.citations())
        assert golden_findings, 'Previously wrong prose must not pass the new structural checks'
        result['runs'][side] = {'evidence_count': len(model.evidence),
                               'evidence_gaps': [k for k, v in model.evidence.items() if v['status'] != 'available'],
                               'checks': {k: {f: v[f] for f in ('status', 'findings', 'facts_omitted', 'mode')}
                                          for k, v in report['sections'].items()},
                               'old_prose_findings': golden_findings,
                               'diagram_sha256': hashlib.sha256(diagrams[side].encode()).hexdigest(),
                               'site_repeat_identical': True}
    impact = json.loads((out / 'b/build/impact.json').read_text(encoding='utf-8'))
    result['coverage_findings'] = impact['coverage']['findings']
    assert not any(f['name'] == 'libcamera::ipa::ipu3::algorithms::Lsc' for f in result['coverage_findings'])
    assert diagrams['a'] != diagrams['b']
    result['lsc_scope_gap_resolved'] = True
    result['diagram_changed'] = True
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out / 'result.json', flush=True)


if __name__ == '__main__':
    main()
