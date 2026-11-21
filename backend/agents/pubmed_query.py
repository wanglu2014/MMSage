

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache

try:
    from Bio import Entrez
    HAS_ENTREZ = True
except ImportError:
    HAS_ENTREZ = False

try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from db_checkers import sapbert_retriever
    _HAS_SAPBERT = True
except ImportError:
    _HAS_SAPBERT = False

from runtime_state import save_json


ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "").strip() or "entrez-not-configured@invalid"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "pubmed"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
_SAPBERT_SYN_CACHE_FILE = CACHE_DIR / "sapbert_agent_synonyms.json"


DEFAULT_SYNONYMS: Dict[str, List[str]] = {}   
_sapbert_syn_cache: Dict[str, List[str]] = {}
_sapbert_syn_loaded = False


def _load_agent_syn_cache():
    global _sapbert_syn_cache, _sapbert_syn_loaded
    if _sapbert_syn_loaded:
        return
    if _SAPBERT_SYN_CACHE_FILE.exists():
        try:
            with open(_SAPBERT_SYN_CACHE_FILE, "r", encoding="utf-8") as f:
                _sapbert_syn_cache = json.load(f)
        except Exception:
            pass
    _sapbert_syn_loaded = True


def _save_agent_syn_cache():
    try:
        save_json(_SAPBERT_SYN_CACHE_FILE, _sapbert_syn_cache)
    except Exception:
        pass


def _get_sapbert_synonyms(entity_name: str, entity_type: str = None) -> List[str]:
    pass
    _load_agent_syn_cache()
    cache_key = f"{entity_name}|{entity_type or 'any'}"
    if cache_key in _sapbert_syn_cache:
        return _sapbert_syn_cache[cache_key]

    syns = [entity_name.replace("_", " ")]
    if _HAS_SAPBERT:
        try:
            hits = sapbert_retriever.retrieve(
                entity_name.replace("_", " "),
                entity_type=entity_type,
                top_k=5, threshold=0.75, exact_first=True,
            )
            for name, _score in hits:
                clean = name.strip()
                if clean and clean.lower() not in {s.lower() for s in syns}:
                    syns.append(clean)
        except Exception:
            pass

    _sapbert_syn_cache[cache_key] = syns
    _save_agent_syn_cache()
    return syns


def _get_cache_key(query: str) -> str:
    pass
    return hashlib.md5(query.encode()).hexdigest()


def _load_cache(key: str) -> Optional[int]:
    pass
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return data.get('count')
        except:
            pass
    return None


def _save_cache(key: str, count: int, query: str):
    pass
    cache_file = CACHE_DIR / f"{key}.json"
    try:
        save_json(cache_file, {"count": count, "query": query, "timestamp": time.time()})
    except:
        pass


def build_pubmed_query(terms: List[str], synonym_map: Optional[Dict] = None) -> str:
    pass
    if synonym_map is None:
        synonym_map = {}

    query_parts = []
    for term in terms:
        term_lower = term.lower().replace('_', ' ')

        
        synonyms = None
        for key, vals in synonym_map.items():
            if key in term_lower or term_lower in key:
                synonyms = vals + [term]
                break
            for val in vals:
                if val.lower() in term_lower:
                    synonyms = vals + [term]
                    break
            if synonyms:
                break

        
        if not synonyms:
            entity_type = None
            
            _disease_hints = ("disease", "syndrome", "disorder", "itis",
                              "osis", "emia", "uria", "pathy", "cancer",
                              "tumor", "carcinoma", "lymphoma", "leukemia")
            if any(kw in term_lower for kw in _disease_hints):
                entity_type = "disease"
            synonyms = _get_sapbert_synonyms(term, entity_type=entity_type)

        unique_syns = list(dict.fromkeys(s for s in synonyms if s))[:4]
        if len(unique_syns) > 1:
            syn_query = ' OR '.join(
                f'"{s}"[Title/Abstract]' for s in unique_syns)
            query_parts.append(f"({syn_query})")
        else:
            query_parts.append(f'"{unique_syns[0]}"[Title/Abstract]')

    return ' AND '.join(query_parts)


def query_pubmed_count(query: str, use_cache: bool = True) -> int:
    pass
    
    cache_key = _get_cache_key(query)
    if use_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached

    if not HAS_ENTREZ:
        
        _save_cache(cache_key, 0, query)
        return 0

    try:
        Entrez.email = ENTREZ_EMAIL
        handle = Entrez.esearch(db="pubmed", term=query, retmax=0)
        record = Entrez.read(handle)
        handle.close()
        count = int(record.get("Count", 0))

        if use_cache:
            _save_cache(cache_key, count, query)

        
        time.sleep(0.35)
        return count
    except Exception:
        if use_cache:
            _save_cache(cache_key, 0, query)
        return 0


def normalize_novelty(count: int, c_max: int = 500) -> float:
    pass
    import math
    if count <= 0:
        return 1.0
    novelty = 1 - math.log(1 + count) / math.log(1 + c_max)
    return max(0.0, min(1.0, novelty))
