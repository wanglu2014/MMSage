"""Look up ChEBI relationships using compact, dictionary-encoded edge columns."""

import csv
from array import array
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Dict

import numpy as np

try:
    from .sapbert_retriever import retrieve
except ImportError:
    from sapbert_retriever import retrieve


CHEBI_PATH = Path(__file__).parent.parent.parent / "data" / "databases" / "chebi_relationships_standardized.csv"
_load_lock = Lock()


def _normalize(name):
    return name.lower().replace("_", " ").replace("-", " ").strip()


@lru_cache(maxsize=1)
def _read_data(path):
    names, relations = {}, {}
    source_ids, target_ids, relation_ids = array("I"), array("I"), array("I")
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                source = (row.get("source_name") or "").strip().lower()
                target = (row.get("target_name") or "").strip().lower()
                relation = (row.get("edge_type") or "").strip().lower()
                source_ids.append(names.setdefault(source, len(names)))
                target_ids.append(names.setdefault(target, len(names)))
                relation_ids.append(relations.setdefault(relation, len(relations)))
    return (tuple(names), tuple(_normalize(name) for name in names), tuple(relations),
            np.asarray(source_ids), np.asarray(target_ids), np.asarray(relation_ids))


def _matches(data, query):
    names, normalized, relations, sources, targets, edge_types = data
    term = _normalize(query)
    name_matches = np.fromiter(
        (bool(term and name and (term in name or name in term)) for name in normalized),
        dtype=bool, count=len(names),
    )
    count, first_rows = 0, []
    if name_matches.any():
        # A common name can match most of the database. Only the first 20 rows
        # contribute to evidence details; keep the full count without storing every hit.
        for start in range(0, len(sources), 65536):
            block = slice(start, start + 65536)
            mask = name_matches[sources[block]] | name_matches[targets[block]]
            count += int(np.count_nonzero(mask))
            if len(first_rows) < 20:
                for offset in np.flatnonzero(mask)[:20 - len(first_rows)]:
                    i = start + offset
                    first_rows.append((names[sources[i]], relations[edge_types[i]], names[targets[i]]))
    return count, first_rows


def check_chebi(metabolite: str, disease: str = "") -> Dict:
    with _load_lock:
        data = _read_data(CHEBI_PATH)
    count, rows = _matches(data, metabolite)
    method = "exact"
    if not count and len(data[0]):
        try:
            for name, score in retrieve(metabolite, entity_type="metabolite", top_k=3, threshold=0.7):
                count, rows = _matches(data, name)
                if count:
                    method = f"sapbert({name},{score:.3f})"
                    break
        except Exception:
            pass

    term = _normalize(metabolite)
    related = set()
    for source, _, target in rows:
        norm_source = _normalize(source)
        matches_source = term and norm_source and (term in norm_source or norm_source in term)
        related.add(target if matches_source else source)
    return {"hit": bool(count), "records": count, "match_method": method,
            "related_metabolites": list(related)[:10],
            "details": [f"{source}--{edge}-->{target}" for source, edge, target in rows[:5]]}
