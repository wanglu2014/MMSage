import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


INDEX_DIR = Path(__file__).parent / "sapbert_index"
_SCORE_BLOCK_ROWS = 1024

_embeddings: Optional[np.ndarray] = None
_mapping: Optional[Dict] = None
_type_indices: Optional[Dict[str, np.ndarray]] = None
_index_lock = threading.Lock()


def _load_index():
    global _embeddings, _mapping, _type_indices
    with _index_lock:
        if _embeddings is not None:
            return

        emb_path = INDEX_DIR / "entity_embeddings.npy"
        map_path = INDEX_DIR / "entity_mapping.json"
        if not emb_path.exists() or not map_path.exists():
            print(f"[SapBERT] Index not found at {INDEX_DIR}. Run build_sapbert_index.py first.")
            _mapping, _type_indices, _embeddings = {}, {}, np.array([])
            return

        embeddings = np.load(emb_path, mmap_mode="r")
        with map_path.open(encoding="utf-8") as f:
            mapping = json.load(f)
        by_type = {}
        for idx_str, info in mapping.items():
            by_type.setdefault(info.get("type", "unknown"), []).append(int(idx_str))
        type_indices = {key: np.array(rows, dtype=np.int64) for key, rows in by_type.items()}
        _mapping, _type_indices, _embeddings = mapping, type_indices, embeddings

        print(f"[SapBERT] Loaded index: {len(embeddings)} entities, "
              f"types: { {k: len(v) for k, v in type_indices.items()} }")


_model = None
_model_lock = threading.Lock()
_model_retry_at = 0.0


def _get_model():
    global _model, _model_retry_at
    with _model_lock:
        if _model is not None:
            return _model
        if time.monotonic() < _model_retry_at:
            raise RuntimeError("SapBERT model temporarily unavailable")
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("cambridgeltl/SapBERT-from-PubMedBERT-fulltext")
        except Exception:
            # Independent evidence lookups share the same model download or import failure.
            _model_retry_at = time.monotonic() + 60
            raise
        print("[SapBERT] Model loaded.")
        return _model


def encode_query(query: str) -> np.ndarray:
    return _get_model().encode([query], normalize_embeddings=True)[0]


def _exact_match(query: str, entity_type: str = None) -> List[str]:
    _load_index()
    q = query.lower().replace("_", " ").replace("-", " ").strip()
    results = []
    indices = range(len(_mapping)) if entity_type is None else _type_indices.get(entity_type, [])
    for idx in indices:
        info = _mapping[str(int(idx))]
        name = info["name"].lower().replace("_", " ").replace("-", " ").strip()
        if q == name or q in name or name in q:
            results.append(info["name"])
    return results


def _ranked_scores(query_emb, entity_type, limit):
    """Keep one score per entity, without duplicating the embedding matrix."""
    indices = _type_indices.get(entity_type)
    count = len(_embeddings) if indices is None else len(indices)
    scores = np.empty(count, dtype=np.result_type(query_emb.dtype, _embeddings.dtype))
    for start in range(0, count, _SCORE_BLOCK_ROWS):
        stop = min(start + _SCORE_BLOCK_ROWS, count)
        rows = slice(start, stop) if indices is None else indices[start:stop]
        scores[start:stop] = _embeddings[rows] @ query_emb

    for i in np.argsort(scores)[::-1][:limit]:
        idx = int(i if indices is None else indices[i])
        yield _mapping[str(idx)]["name"], float(scores[i])


def retrieve(
    query: str,
    entity_type: str = None,
    top_k: int = 10,
    threshold: float = 0.7,
    exact_first: bool = True,
) -> List[Tuple[str, float]]:
    _load_index()
    if len(_embeddings) == 0:
        return []

    results = []
    if exact_first:
        exact_hits = _exact_match(query, entity_type)
        results = [(name, 1.0) for name in exact_hits[:top_k]]
        if len(results) >= top_k:
            return results[:top_k]

    exact_names = {r[0] for r in results}
    for name, score in _ranked_scores(encode_query(query), entity_type, top_k * 2):
        if score < threshold:
            break
        if name not in exact_names:
            results.append((name, score))
            exact_names.add(name)
        if len(results) >= top_k:
            break
    return results[:top_k]


def retrieve_batch(
    queries: List[str],
    entity_type: str = None,
    top_k: int = 5,
    threshold: float = 0.7,
) -> Dict[str, List[Tuple[str, float]]]:
    _load_index()
    if not queries or len(_embeddings) == 0:
        return {q: [] for q in queries}

    query_embs = _get_model().encode(queries, normalize_embeddings=True)
    results = {}
    for query, query_emb in zip(queries, query_embs):
        hits = []
        for name, score in _ranked_scores(query_emb, entity_type, top_k):
            if score < threshold:
                break
            hits.append((name, score))
        results[query] = hits
    return results
