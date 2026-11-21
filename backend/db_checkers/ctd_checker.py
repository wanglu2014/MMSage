import csv
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Dict

try:
    from .sapbert_retriever import retrieve
except ImportError:
    from sapbert_retriever import retrieve


CTD_PATH = Path(__file__).parent.parent.parent / "data" / "databases" / "CTD_chemicals_diseases.tsv"

DISEASE_SYNONYMS = {
    'ibd': ['inflammatory bowel disease', 'crohn', "crohn's disease", 'ulcerative colitis'],
    'uc': ['ulcerative colitis'],
    'cd': ["crohn's disease", 'crohn disease'],
    't2d': ['type 2 diabetes', 'diabetes mellitus type 2'],
    'crc': ['colorectal cancer', 'colon cancer'],
    'nafld': ['non-alcoholic fatty liver', 'nonalcoholic fatty liver'],
    'nash': ['nonalcoholic steatohepatitis', 'non-alcoholic steatohepatitis'],
}


def _normalize(value):
    return value.lower().replace('_', ' ').replace('-', ' ').strip()


def _matches(query, target):
    return bool(query and target) and (query in target or target in query)


@lru_cache(maxsize=8)
def _disease_rows(path, mtime_ns, size, disease):
    # A run queries many metabolites for the same disease. Spool the relevant
    # rows once, keeping their source order and bounding memory for broad terms.
    result = tempfile.TemporaryFile(mode="w+t", encoding="utf-8", newline="")
    terms = [_normalize(disease)]
    terms.extend(_normalize(s) for s in DISEASE_SYNONYMS.get(disease.lower().strip(), []))

    @lru_cache(maxsize=8192)
    def selected(target):
        normalized = _normalize(target)
        return any(_matches(term, normalized) for term in terms)

    try:
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source, delimiter="\t")
            writer = csv.writer(result, delimiter="\t")
            for row in reader:
                target = (row.get("target_name") or "").strip().lower()
                if selected(target):
                    chemical = (row.get("source_name") or "").strip().lower()
                    edge = (row.get("edge_type") or "").strip().lower()
                    writer.writerow((chemical, edge, target))
        result.flush()
    except BaseException:
        result.close()
        raise
    return result, threading.Lock()


def _find(path, stamp, metabolite, disease):
    rows, lock = _disease_rows(path, stamp.st_mtime_ns, stamp.st_size, disease)
    query = _normalize(metabolite)
    count = 0
    edges = set()
    details = []
    with lock:
        rows.seek(0)
        for chemical, edge, target in csv.reader(rows, delimiter="\t"):
            if _matches(query, _normalize(chemical)):
                count += 1
                if edge:
                    edges.add(edge)
                if len(details) < 5:
                    details.append(f"{chemical}--{edge}-->{target}")
    return {"hit": bool(count), "records": count, "match_method": "exact",
            "edge_types": list(edges), "details": details}


def check_ctd(metabolite: str, disease: str) -> Dict:
    try:
        stamp = CTD_PATH.stat()
    except FileNotFoundError:
        return {"hit": False, "records": 0, "match_method": "exact", "edge_types": [], "details": []}

    result = _find(CTD_PATH, stamp, metabolite, disease)
    if result["hit"]:
        return result
    try:
        met_hits = retrieve(metabolite, entity_type="metabolite", top_k=3, threshold=0.7)
        dis_hits = retrieve(disease, entity_type="disease", top_k=3, threshold=0.7)
        chemicals = dict.fromkeys([metabolite, *(name for name, score in met_hits)])
        diseases = dict.fromkeys([disease, *(name for name, score in dis_hits)])
        for chemical in chemicals:
            for condition in diseases:
                if (chemical, condition) == (metabolite, disease):
                    continue
                match = _find(CTD_PATH, stamp, chemical, condition)
                if match["hit"]:
                    match["match_method"] = f"sapbert(m={chemical},d={condition})"
                    return match
    except Exception:
        pass
    return result
