import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict

try:
    from .sapbert_retriever import retrieve
except ImportError:
    from sapbert_retriever import retrieve


BACDIVE_PATH = Path(__file__).parent.parent.parent / "data" / "databases" / "bacdive_edges.tsv"


def _normalize(value):
    return value.lower().replace('_', ' ').replace('-', ' ').strip()


@lru_cache(maxsize=256)
def _summary(path, mtime_ns, size, bacteria):
    # BacDive evidence depends only on the microbe and recurs across metabolites.
    query = _normalize(bacteria)

    @lru_cache(maxsize=4096)
    def matches(name):
        target = _normalize(name)
        return bool(query and target) and (query in target or target in query)

    count = 0
    environments = set()
    details = []
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            microbe = (row.get("source_name") or "").strip().lower()
            if not (matches(microbe) or matches(row.get("standard_sourcename") or "")):
                continue
            count += 1
            if count <= 20:
                target = (row.get("target_name") or "").strip().lower()
                if target:
                    environments.add(target)
                if count <= 5:
                    edge = (row.get("edge_type") or "").strip().lower()
                    details.append(f"{microbe}--{edge}-->{target}")
    return count, tuple(environments)[:10], tuple(details)


def check_bacdive(bacteria: str, metabolite: str) -> Dict:
    count, environments, details = 0, (), ()
    method = "exact"
    try:
        stamp = BACDIVE_PATH.stat()
    except FileNotFoundError:
        stamp = None
    if stamp is not None:
        version = (BACDIVE_PATH, stamp.st_mtime_ns, stamp.st_size)
        count, environments, details = _summary(*version, bacteria)
        if not count:
            try:
                candidates = retrieve(bacteria, entity_type="microbe", top_k=3, threshold=0.7)
                for name, score in candidates:
                    count, environments, details = _summary(*version, name)
                    if count:
                        method = f"sapbert({name},{score:.3f})"
                        break
            except Exception:
                pass
    return {"hit": bool(count), "records": count, "match_method": method,
            "environments": list(environments), "details": list(details)}
