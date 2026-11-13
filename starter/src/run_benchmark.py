from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STARTER_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = PROJECT_ROOT / "starter" / "benchmark" / "benchmark_calculus_v1.json"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.json"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "benchmark"
STRATEGIES = ("A", "B", "C")


def normalize(text: str) -> str:
    """Normalize whitespace and case for exact-evidence matching."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def validate_questions(benchmark: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    questions = benchmark.get("questions")
    if not isinstance(questions, list) or len(questions) < 20:
        raise ValueError("Benchmark must have at least 20 questions")
    ids = [q.get("id") for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate or missing question IDs")
    split_counts = Counter(q.get("split") for q in questions)
    if split_counts["dev"] < 15 or split_counts["test"] < 5:
        raise ValueError(f"Expected at least 15 dev / 5 test, got {dict(split_counts)}")
    counted_pages = set(manifest.get("counted_pages", []))
    source = manifest.get("source_id")
    filtered = []
    for q in questions:
        qid = q.get("id", "UNKNOWN")
        for key in ("id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote"):
            if not q.get(key):
                raise ValueError(f"{qid}: missing {key}")
        if q["split"] not in {"dev", "test"}:
            raise ValueError(f"{qid}: invalid split")
        if q["gold_source_id"] != source:
            raise ValueError(f"{qid}: gold source does not match manifest")
        if q["gold_page"] not in counted_pages:
            raise ValueError(f"{qid}: gold page not in corpus")
        f = q.get("filter")
        if f is not None:
            if not isinstance(f, dict) or not f:
                raise ValueError(f"{qid}: filter must be null or nonempty object")
            if not set(f).issubset({"section", "source", "document_id", "page"}):
                raise ValueError(f"{qid}: unsupported filter fields: {set(f)}")
            filtered.append(q)
    if len(filtered) < 3 or not any(q["split"] == "test" for q in filtered):
        raise ValueError("Need >=3 filter questions including >=1 test")
    return questions


def strict_hit(result: dict[str, Any], question: dict[str, Any]) -> bool:
    """Gold source, gold physical page and complete quote in same chunk."""
    metadata = result.get("metadata") or {}
    return (
        str(result.get("document_id") or metadata.get("document_id")) == str(question["gold_source_id"])
        and str(result.get("page") or metadata.get("page")) == str(question["gold_page"])
        and normalize(question["evidence_quote"]) in normalize(result.get("text", ""))
    )


def score_record(q: dict[str, Any], results: list[dict[str, Any]], filters: dict[str, Any] | None) -> dict[str, Any]:
    hits = [strict_hit(r, q) for r in results]
    filter_ok = all(
        str((r.get("metadata") or {}).get(key)) == str(value)
        for r in results
        for key, value in (filters or {}).items()
    )
    return {
        "id": q["id"],
        "split": q["split"],
        "question": q["question"],
        "type": q.get("type"),
        "expected_answer": q["expected_answer"],
        "gold_source_id": q["gold_source_id"],
        "gold_page": q["gold_page"],
        "evidence_quote": q["evidence_quote"],
        "requested_filter": q.get("filter"),
        "applied_filter": filters,
        "hit_at_1_strict": bool(hits[:1] and hits[0]),
        "evidence_hit_at_3_strict": any(hits[:3]),
        "filter_compliant": filter_ok if filters is not None else None,
        "needs_manual_evidence_review": not any(hits[:3]),
        "results": [
            {"rank": i + 1, **r, "strict_evidence_hit": hits[i]}
            for i, r in enumerate(results)
        ],
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    hit1 = sum(bool(x["hit_at_1_strict"]) for x in records)
    hit3 = sum(bool(x["evidence_hit_at_3_strict"]) for x in records)
    checked = [x for x in records if x["applied_filter"] is not None]
    compliant = sum(bool(x["filter_compliant"]) for x in checked)
    return {
        "questions": n,
        "hit_at_1_strict": {"numerator": hit1, "denominator": n, "rate": round(hit1 / n, 4) if n else None},
        "evidence_hit_at_3_strict": {"numerator": hit3, "denominator": n, "rate": round(hit3 / n, 4) if n else None},
        "filter_compliance": {
            "numerator": compliant, "denominator": len(checked),
            "rate": round(compliant / len(checked), 4) if checked else None,
        },
        "questions_needing_manual_evidence_review": [x["id"] for x in records if x["needs_manual_evidence_review"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Day 06 retrieval benchmark against existing pgvector vectors")
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--confirm-frozen", action="store_true", help="Required on test: confirms strategy was frozen on dev")
    args = parser.parse_args()
    if args.split == "test" and not args.confirm_frozen:
        parser.error("Before running test, freeze your strategy on dev; rerun with --confirm-frozen")

    benchmark = read_json(BENCHMARK_PATH)
    manifest = read_json(MANIFEST_PATH)
    questions = [q for q in validate_questions(benchmark, manifest) if q["split"] == args.split]
    if not questions:
        raise ValueError("No questions in selected split")

    load_dotenv(STARTER_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL", "").strip()
    model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3").strip()
    if not database_url:
        raise ValueError("DATABASE_URL missing from starter/.env")

    # Import only after validating benchmark and environment.
    from .embeddings import MyEmbedder
    from .store import PgVectorStore

    embedder = MyEmbedder(model_name)
    store = PgVectorStore(database_url, embedder.dimensions)
    for strategy in ("A", "B"):
        if store.count(strategy) == 0:
            raise RuntimeError(f"No stored vectors for {strategy}; run Phase 4 ingestion first")

    traces: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATEGIES}
    timings: dict[str, float] = {s: 0.0 for s in STRATEGIES}
    embedding_seconds = 0.0
    for index, q in enumerate(questions, 1):
        tick = time.perf_counter()
        vector = embedder.embed_query(q["question"])
        embedding_seconds += time.perf_counter() - tick
        for strategy in STRATEGIES:
            # A/B always unfiltered; C uses the filter only when explicitly present.
            applied = q.get("filter") if strategy == "C" else None
            tick = time.perf_counter()
            results = store.search(strategy, vector, top_k=3, filters=applied)
            elapsed = time.perf_counter() - tick
            timings[strategy] += elapsed
            record = score_record(q, results, applied)
            record["search_seconds"] = round(elapsed, 6)
            traces[strategy].append(record)
        print(f"[{index}/{len(questions)}] {q['id']} retrieved on A/B/C")

    out_dir = OUTPUT_ROOT / args.split
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "benchmark_file": str(BENCHMARK_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "embedding_model": embedder.model_name,
        "embedding_dimensions": embedder.dimensions,
        "retrieval_top_k": 3,
        "search_metric": "pgvector cosine similarity",
        "C_without_filter_behavior": "same search as B with no filter",
        "query_embedding_total_seconds": round(embedding_seconds, 3),
        "strategies": {},
        "metric_note": "Strict automatic hits require a single chunk with full gold evidence and matching source/page. Manual equivalent-evidence review and audit are still required.",
    }
    for strategy in STRATEGIES:
        save_json(out_dir / f"retrieval_{strategy}.json", traces[strategy])
        summary["strategies"][strategy] = {
            **summarize(traces[strategy]),
            "search_total_seconds": round(timings[strategy], 3),
            "average_search_seconds_per_question": round(timings[strategy] / len(questions), 6),
            "stored_vectors_used": store.count(strategy),
        }
    save_json(out_dir / "summary.json", summary)
    print("\n=== BENCHMARK RESULTS (strict automatic) ===")
    for strategy in STRATEGIES:
        s = summary["strategies"][strategy]
        print(f"{strategy}: Hit@1 {s['hit_at_1_strict']['numerator']}/{s['hit_at_1_strict']['denominator']}; "
              f"Evidence Hit@3 {s['evidence_hit_at_3_strict']['numerator']}/{s['evidence_hit_at_3_strict']['denominator']}; "
              f"filter compliance {s['filter_compliance']['numerator']}/{s['filter_compliance']['denominator']}")
    print(f"Saved traces and summary in {out_dir}")
    print("Next: audit false negatives, coherence, metadata and grounding manually before final conclusions.")


if __name__ == "__main__":
    main()
