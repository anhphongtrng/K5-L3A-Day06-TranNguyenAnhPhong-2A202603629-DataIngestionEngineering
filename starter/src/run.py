from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from .chunking import by_paragraph, fixed_size
from .ingestion import attach_sections, load_from_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STARTER_ROOT = Path(__file__).resolve().parents[1]


def save_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def make_collections():
    pages = load_from_manifest(PROJECT_ROOT / "data" / "manifest.json", PROJECT_ROOT)
    segments = attach_sections(pages, PROJECT_ROOT / "data" / "section_map.json")
    a = [c for page in segments for c in fixed_size(page, size=500, overlap=50)]
    b = [c for page in segments for c in by_paragraph(page, max_size=500)]
    for strategy, chunks in (("A", a), ("B", b)):
        if not chunks:
            raise ValueError(f"No chunks generated for strategy {strategy}")
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError(f"Duplicate chunk IDs for {strategy}")
        if not all(isinstance(c.metadata.get("section"), str) for c in chunks):
            raise ValueError(f"Section metadata missing for {strategy}")
    return pages, segments, a, b


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate PDF, sections and chunks without Docker/model")
    parser.add_argument("--model", default=None, help="Override EMBEDDING_MODEL from .env")
    args = parser.parse_args()

    started = time.perf_counter()
    pages, segments, a, b = make_collections()
    print(f"Corpus: {len(pages)} physical pages -> {len(segments)} segments")
    for name, chunks in (("A fixed", a), ("B paragraph", b)):
        print(f"{name}: {len(chunks)} chunks; section distribution: {dict(Counter(c.metadata['section'] for c in chunks))}")

    stats = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "physical_pages": len(pages),
        "section_segments": len(segments),
        "strategies": {
            "A": {"chunking": "fixed", "size_chars": 500, "overlap_chars": 50, "chunks": len(a)},
            "B": {"chunking": "paragraph", "max_chars": 500, "chunks": len(b)},
            "C": {"chunking": "same as B", "metadata_filter": "section", "chunks": len(b)},
        },
        "section_counts_A": dict(Counter(c.metadata['section'] for c in a)),
        "section_counts_B": dict(Counter(c.metadata['section'] for c in b)),
    }
    out_dir = PROJECT_ROOT / "artifacts" / "ingestion"
    if args.dry_run:
        stats["status"] = "dry_run_validated_no_database_writes"
        stats["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        save_json(out_dir / "dry_run_stats.json", stats)
        print("Dry-run OK; no model loaded, database untouched")
        return

    load_dotenv(STARTER_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL", "").strip()
    model_name = (args.model or os.getenv("EMBEDDING_MODEL") or "BAAI/bge-m3").strip()
    if not database_url:
        raise ValueError("DATABASE_URL is missing from starter/.env")
    from .embeddings import MyEmbedder
    from .store import PgVectorStore

    embedder = MyEmbedder(model_name)
    store = PgVectorStore(database_url, embedder.dimensions)
    store.create_schema()
    stats["embedding_model"] = embedder.model_name
    stats["dimensions"] = embedder.dimensions
    stats["similarity"] = "cosine"

    for strategy, chunks in (("A", a), ("B", b)):
        tick = time.perf_counter()
        print(f"Embedding {strategy}: {len(chunks)} chunks...")
        vectors = embedder.embed_documents([c.text for c in chunks])
        store.upsert(strategy, chunks, vectors)
        stored = store.count(strategy)
        if stored != len(chunks):
            raise RuntimeError(f"Count mismatch {strategy}: expected {len(chunks)}, got {stored}")
        stats["strategies"][strategy]["stored_vectors"] = stored
        stats["strategies"][strategy]["seconds"] = round(time.perf_counter() - tick, 3)
        print(f"Stored {strategy}: {stored} vectors")

    # C reuses the B vectors and applies section filtering only at search time.
    question = "What is an inverse function?"
    query_vector = embedder.embed_query(question)
    smoke = {
        "query": question,
        "A": store.search("A", query_vector, 3),
        "B": store.search("B", query_vector, 3),
        "C_section_1_4": store.search("C", query_vector, 3, {"section": "1.4"}),
    }
    if any(r["metadata"].get("section") != "1.4" for r in smoke["C_section_1_4"]):
        raise RuntimeError("Section filter returned out-of-scope chunks")
    save_json(out_dir / "smoke_retrieval.json", smoke)
    stats["status"] = "ingestion_complete"
    stats["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    save_json(out_dir / "stats.json", stats)
    print(f"Ingestion OK. Saved: {out_dir / 'stats.json'}")
    print("Next: implement benchmark evaluation using dev/test; do not tune on test.")


if __name__ == "__main__":
    main()
