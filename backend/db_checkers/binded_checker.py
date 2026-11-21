"""Microbe and compound evidence in BindedDB."""

import csv
import heapq
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Dict, Optional


BINDED_DB_PATH = Path(__file__).parent.parent.parent / "data" / "databases" / "binded_database_anno_named.csv"
_load_lock = Lock()
_sapbert_available: Optional[bool] = None


@lru_cache(maxsize=1)
def _read_data(path):
    by_species = {}
    if not path.exists():
        return by_species

    # Most rows repeat the same species, compound, accession and source labels.
    labels = {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            species = row.get("species.name", "")
            if not species:
                continue
            species = labels.setdefault(species, species)
            compound = row.get("Compound_Name", "")
            cid = row.get("cid.ID", "")
            source = row.get("sourcename", "")
            genus = row.get("genus.name", "")
            record = (index, species, labels.setdefault(compound, compound),
                      labels.setdefault(cid, cid), labels.setdefault(source, source),
                      labels.setdefault(genus, genus))
            by_species.setdefault(species, []).append(record)
    return by_species


def _species_rows(data, names):
    groups = (rows for species, rows in data.items()
              if any(_fuzzy_match(name, species) for name in names))
    # A substring can match multiple species. Merge their rows in original CSV order.
    return heapq.merge(*groups)


def _normalize(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ").strip()


def _fuzzy_match(query: str, target: str) -> bool:
    q, t = _normalize(query), _normalize(target)
    return bool(q and t and (q in t or t in q))


def _pair_result(data, microbes, metabolites, method):
    count = 0
    sources = set()
    details = []
    for _, species, compound, cid, source, genus in _species_rows(data, microbes):
        if not compound or compound == "NA":
            continue
        if any(_fuzzy_match(name, compound) for name in metabolites):
            count += 1
            sources.add(source)
            if len(details) < 10:
                details.append({"species": species, "compound": compound, "cid": cid,
                                "source": source, "genus": genus})
    return {"hit": bool(count), "records": count, "sources": list(sources),
            "match_method": method if count else "none", "match_details": details}


def check_binded_microbe_metabolite(microbe: str, metabolite: str) -> Dict:
    global _sapbert_available
    with _load_lock:
        data = _read_data(BINDED_DB_PATH)
    direct = _pair_result(data, [microbe], [metabolite], "exact")
    if direct["hit"] or not data or _sapbert_available is False:
        return direct
    try:
        from .sapbert_retriever import retrieve
        _sapbert_available = True
        microbes = retrieve(microbe, entity_type="microbe", top_k=5, threshold=0.85)
        metabolites = retrieve(metabolite, entity_type="metabolite", top_k=5, threshold=0.85)
        if microbes and metabolites:
            return _pair_result(data, [name for name, _ in microbes],
                                [name for name, _ in metabolites], "semantic")
    except Exception as e:
        _sapbert_available = False
        print(f"[BindedDB] SapBERT unavailable ({e}), skipping semantic matching for all future calls")
    return direct


def check_binded_microbe(microbe: str) -> Dict:
    with _load_lock:
        data = _read_data(BINDED_DB_PATH)
    compounds, sources = set(), set()
    count = 0
    for _, _, compound, _, source, _ in _species_rows(data, [microbe]):
        if compound and compound != "NA":
            compounds.add(compound)
        sources.add(source)
        count += 1
    return {"hit": bool(count), "records": count, "compounds": sorted(compounds)[:50],
            "sources": list(sources)}
