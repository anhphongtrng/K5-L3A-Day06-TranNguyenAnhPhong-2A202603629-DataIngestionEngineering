"""Prepare HUMAN-review CSVs from Day06 retrieval traces. Never assigns audit scores.
Run from starter/: python scripts/prepare_audit.py --stage dev
Then after frozen test: python scripts/prepare_audit.py --stage test
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'artifacts'
BENCHMARK = ROOT / 'starter' / 'benchmark' / 'benchmark_calculus_v1.json'
OUTPUT = ARTIFACTS / 'audit'
STRATEGIES = ('A', 'B', 'C')


def read_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f'Missing {path}. Run the relevant benchmark first.')
    return json.loads(path.read_text(encoding='utf-8'))


def save_csv(path: Path, headers: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f'Saved {path.relative_to(ROOT)} ({len(rows)} rows)')


def read_traces(split: str):
    traces = {}
    for strategy in STRATEGIES:
        records = read_json(ARTIFACTS / 'benchmark' / split / f'retrieval_{strategy}.json')
        if not isinstance(records, list):
            raise ValueError(f'{split}/{strategy}: expected JSON list')
        traces[strategy] = {r['id']: r for r in records}
    return traces


def excerpt(text, max_chars=600):
    s = ' '.join(str(text or '').split())
    return s[:max_chars] + ('...' if len(s) > max_chars else '')


def dev_outputs():
    traces = read_traces('dev')
    questions = [q for q in read_json(BENCHMARK)['questions'] if q['split'] == 'dev']
    # Preselect SAME 10 gold source positions for every strategy; user must check selections.
    sample = questions[:10]
    coherence = []
    for q in sample:
        for strategy in STRATEGIES:
            record = traces[strategy].get(q['id'])
            if record is None:
                raise ValueError(f'Missing dev {strategy}/{q["id"]}')
            hits = record.get('results') or []
            on_gold_page = [r for r in hits if str(r.get('page')) == str(q['gold_page'])]
            chosen = next((r for r in on_gold_page if r.get('strict_evidence_hit')), None)
            if chosen is None:
                chosen = on_gold_page[0] if on_gold_page else (hits[0] if hits else {})
            coherence.append({
                'source_position_id': q['id'], 'source_page': q['gold_page'],
                'source_evidence': q['evidence_quote'], 'strategy': strategy,
                'candidate_chunk_id': chosen.get('chunk_id', ''),
                'candidate_chunk_page': chosen.get('page', ''),
                'candidate_chunk_text_preview': excerpt(chosen.get('text', '')),
                'review_note': 'Select the chunk covering the SAME source evidence; search stored chunks if top-3 misses it.',
                'verified_chunk_id': '', 'score_0_1_2': '', 'reason': '',
            })
    save_csv(OUTPUT/'coherence_review.csv', [
        'source_position_id','source_page','source_evidence','strategy','candidate_chunk_id',
        'candidate_chunk_page','candidate_chunk_text_preview','review_note',
        'verified_chunk_id','score_0_1_2','reason'
    ], coherence)
    failures = []
    for strategy in STRATEGIES:
        for q in questions:
            r = traces[strategy][q['id']]
            if not r.get('evidence_hit_at_3_strict') or not r.get('hit_at_1_strict'):
                failures.append({
                    'strategy':strategy,'question_id':q['id'], 'question':q['question'],
                    'gold_page':q['gold_page'], 'gold_evidence':q['evidence_quote'],
                    'hit1_auto':r.get('hit_at_1_strict'), 'hit3_auto':r.get('evidence_hit_at_3_strict'),
                    'top3_chunk_ids':' | '.join(str(x.get('chunk_id','')) for x in r.get('results',[])),
                    'equivalent_evidence_found_yes_no':'','confirmed_hit1':'','confirmed_hit3':'',
                    'failure_cause':'','reviewer_reason':''
                })
    save_csv(OUTPUT/'dev_false_negative_review.csv', [
        'strategy','question_id','question','gold_page','gold_evidence','hit1_auto',
        'hit3_auto','top3_chunk_ids','equivalent_evidence_found_yes_no',
        'confirmed_hit1','confirmed_hit3','failure_cause','reviewer_reason'
    ], failures)


def test_outputs():
    traces=read_traces('test')
    questions=[q for q in read_json(BENCHMARK)['questions'] if q['split']=='test']
    if len(questions)<5:
        raise ValueError('Expected 5 test questions')
    metadata=[]
    grounding=[]
    for strategy in STRATEGIES:
        for q in questions:
            r=traces[strategy].get(q['id'])
            if r is None:
                raise ValueError(f'Missing test {strategy}/{q["id"]}')
            results=r.get('results') or []
            grounding.append({
                'strategy':strategy,'question_id':q['id'],'question':q['question'],
                'expected_answer':q['expected_answer'],'gold_page':q['gold_page'],
                'gold_evidence':q['evidence_quote'],
                'top3_preview':' | '.join(f"#{i+1} p{x.get('page')} {excerpt(x.get('text'),180)}" for i,x in enumerate(results[:3])),
                'score_0_1_2':'','reason':'','supporting_chunk_ids':'',
                'source_traceable_yes_no':''
            })
            for rank,x in enumerate(results[:3],1):
                m=x.get('metadata') or {}
                metadata.append({
                    'strategy':strategy,'question_id':q['id'],'rank':rank,
                    'chunk_id':x.get('chunk_id',''),'source':x.get('source',''),
                    'document_id':x.get('document_id',''), 'page':x.get('page',''),
                    'section':m.get('section',''),'requested_filter':json.dumps(q.get('filter'),ensure_ascii=False),
                    'text_preview':excerpt(x.get('text'),300),
                    'source_correct_yes_no':'','page_correct_yes_no':'',
                    'section_correct_yes_no':'','complete_and_correct_yes_no':'',
                    'reason':''
                })
    save_csv(OUTPUT/'test_metadata_review.csv', [
        'strategy','question_id','rank','chunk_id','source','document_id','page','section',
        'requested_filter','text_preview','source_correct_yes_no','page_correct_yes_no',
        'section_correct_yes_no','complete_and_correct_yes_no','reason'
    ],metadata)
    save_csv(OUTPUT/'test_grounding_review.csv', [
        'strategy','question_id','question','expected_answer','gold_page','gold_evidence',
        'top3_preview','score_0_1_2','reason','supporting_chunk_ids','source_traceable_yes_no'
    ],grounding)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['dev','test','all'],required=True)
    args=parser.parse_args()
    if args.stage in ('dev','all'):dev_outputs()
    if args.stage in ('test','all'):test_outputs()
    print('Audit forms created. Scores must be entered after MANUAL inspection; no auto-judgment was performed.')

if __name__=='__main__':main()
