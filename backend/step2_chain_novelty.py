

import json
import os
import math
import hashlib
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from knowledge_pump import KnowledgePump

try:
    from Bio import Entrez
    HAS_ENTREZ = True
except ImportError:
    HAS_ENTREZ = False

try:
    from db_checkers import sapbert_retriever
    HAS_SAPBERT = True
except ImportError:
    HAS_SAPBERT = False



ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "").strip() or "entrez-not-configured@invalid"
ENTREZ_API_KEY = None
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "pubmed_cache.json"
SAPBERT_SYN_CACHE_FILE = CACHE_DIR / "sapbert_step2_synonyms.json"
DEFAULT_DISEASE = "IBD"
QUERY_DELAY_S = 0.35

EXPERIMENTAL_FILTER = ' AND ("in vivo" OR "in vitro" OR "mouse" OR "mice" OR "cell line" OR "experiment" OR "clinical trial")'




_sapbert_syn_cache: Dict[str, List[str]] = {}
_sapbert_syn_cache_loaded = False


def _load_sapbert_syn_cache():
    global _sapbert_syn_cache, _sapbert_syn_cache_loaded
    if _sapbert_syn_cache_loaded:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if SAPBERT_SYN_CACHE_FILE.exists():
        try:
            with open(SAPBERT_SYN_CACHE_FILE, "r", encoding="utf-8") as f:
                _sapbert_syn_cache = json.load(f)
        except Exception:
            _sapbert_syn_cache = {}
    _sapbert_syn_cache_loaded = True


def _save_sapbert_syn_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SAPBERT_SYN_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_sapbert_syn_cache, f, indent=2, ensure_ascii=False)


def _sapbert_synonyms(entity_name: str, entity_type: str = None) -> List[str]:
    pass
    _load_sapbert_syn_cache()
    cache_key = f"{entity_name}|{entity_type or 'any'}"
    if cache_key in _sapbert_syn_cache:
        return _sapbert_syn_cache[cache_key]

    syns = [entity_name.replace("_", " ")]
    if HAS_SAPBERT:
        try:
            hits = sapbert_retriever.retrieve(
                entity_name.replace("_", " "),
                entity_type=entity_type,
                top_k=5,
                threshold=0.75,
                exact_first=True,
            )
            for name, _score in hits:
                clean = name.strip()
                if clean and clean.lower() not in {s.lower() for s in syns}:
                    syns.append(clean)
        except Exception:
            pass

    _sapbert_syn_cache[cache_key] = syns
    _save_sapbert_syn_cache()
    return syns




@dataclass
class EdgeCooccurrence:
    source: str
    target: str
    relation: str
    cooccurrence: int
    query: str = ""

@dataclass
class ChainNoveltyResult:
    bacteria: str
    metabolite: str
    
    chain_path: List[str] = field(default_factory=list)
    chain_path_str: str = ""
    disease: str = DEFAULT_DISEASE
    query_terms: List[str] = field(default_factory=list)
    has_path: bool = False
    
    chain_count: int = 0
    chain_novelty: float = 1.0
    chain_query: str = ""
    
    edge_cooccurrences: List[Dict[str, Any]] = field(default_factory=list)
    bottleneck_edge: Optional[Dict[str, Any]] = None
    
    all_paths_info: List[Dict[str, Any]] = field(default_factory=list)




_pubmed_cache: Dict[str, int] = {}
_cache_loaded = False


def _load_cache() -> None:
    pass
    global _pubmed_cache, _cache_loaded
    if _cache_loaded:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                _pubmed_cache = json.load(f)
            print(f"Loaded PubMed cache: {len(_pubmed_cache)} entries")
        except Exception:
            _pubmed_cache = {}
    _cache_loaded = True


def _save_cache() -> None:
    pass
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(_pubmed_cache, f, indent=2, ensure_ascii=False)


def _cache_key(query: str) -> str:
    pass
    return hashlib.md5(query.encode('utf-8')).hexdigest()


def build_pubmed_query(terms: List[str], synonym_map: Dict[str, List[str]] = None) -> str:
    pass
    if synonym_map is None:
        synonym_map = {}

    groups = []
    for term in terms:
        
        synonyms = synonym_map.get(term)
        if not synonyms:
            term_lower = term.lower().strip()
            for key, vals in synonym_map.items():
                if key.lower().replace('_', ' ') == term_lower.replace('_', ' '):
                    synonyms = vals
                    break

        
        if not synonyms:
            entity_type = None
            tl = term.lower().replace("_", " ")
            
            _disease_hints = ("disease", "syndrome", "disorder", "itis",
                              "osis", "emia", "uria", "pathy", "cancer",
                              "tumor", "carcinoma", "lymphoma", "leukemia")
            if any(kw in tl for kw in _disease_hints):
                entity_type = "disease"
            synonyms = _sapbert_synonyms(term, entity_type=entity_type)

        or_parts = [f'"{s}"' for s in synonyms[:4]]
        if len(or_parts) == 1:
            groups.append(or_parts[0])
        else:
            groups.append(f"({' OR '.join(or_parts)})")

    return " AND ".join(groups)


def query_pubmed_count(
    query: str,
    use_cache: bool = True,
) -> int:
    pass
    _load_cache()

    key = _cache_key(query)
    if use_cache and key in _pubmed_cache:
        return _pubmed_cache[key]

    if not HAS_ENTREZ:
        print(f"  [WARN] Biopython not installed, returning 0 for: {query[:80]}...")
        return 0

    Entrez.email = ENTREZ_EMAIL
    if ENTREZ_API_KEY:
        Entrez.api_key = ENTREZ_API_KEY

    try:
        time.sleep(QUERY_DELAY_S)
        handle = Entrez.esearch(db="pubmed", term=query, retmax=0)
        record = Entrez.read(handle)
        handle.close()
        count = int(record.get("Count", 0))
    except Exception as e:
        print(f"  [WARN] PubMed query failed: {e}. Query: {query[:80]}...")
        count = 0

    _pubmed_cache[key] = count
    return count




def _get_node_label(kg: KnowledgePump, node_id: str) -> str:
    pass
    node = kg.get_node(node_id)
    if node:
        return node.get('label', node_id)
    return node_id


def _kg_id_to_pubmed_term(node_id: str, bacteria_orig: str, metabolite_orig: str) -> str:
    pass
    
    bact_normalized = bacteria_orig.lower().replace("_", " ").replace("-", " ")
    node_normalized = node_id.lower().replace("_", " ")
    if node_normalized == bact_normalized or node_normalized == bact_normalized.split()[0]:
        return bacteria_orig.replace("_", " ")

    
    met_normalized = metabolite_orig.lower().replace("_", " ").replace("-", " ")
    if node_normalized == met_normalized:
        return metabolite_orig  

    
    return node_id.replace("_", " ")


def _compute_pairwise_counts(
    bacteria: str,
    metabolite: str,
    disease: str,
    synonym_map: Dict[str, List[str]],
    path_node_labels: List[str] = None,
) -> Dict[str, int]:
    pass
    counts = {}

    
    q = build_pubmed_query([bacteria, metabolite], synonym_map)
    counts['pair_bm'] = query_pubmed_count(q)
    counts['pair_bm_exp'] = query_pubmed_count(q + EXPERIMENTAL_FILTER)

    
    q = build_pubmed_query([bacteria, metabolite, disease], synonym_map)
    counts['triple_bmd'] = query_pubmed_count(q)
    counts['triple_bmd_exp'] = query_pubmed_count(q + EXPERIMENTAL_FILTER)

    
    q = build_pubmed_query([bacteria, disease], synonym_map)
    counts['pair_bd'] = query_pubmed_count(q)

    
    q = build_pubmed_query([metabolite, disease], synonym_map)
    counts['pair_md'] = query_pubmed_count(q)
    counts['pair_md_exp'] = query_pubmed_count(q + EXPERIMENTAL_FILTER)

    
    if path_node_labels and len(path_node_labels) > 2:
        q = build_pubmed_query(path_node_labels + [disease], synonym_map)
        counts['full_chain'] = query_pubmed_count(q)
        counts['full_chain_exp'] = query_pubmed_count(q + EXPERIMENTAL_FILTER)

    return counts


def _aggregate_chain_count(pairwise: Dict[str, int]) -> int:
    pass
    return pairwise.get('triple_bmd_exp', 0)


def find_best_chain(
    bacteria: str,
    metabolite: str,
    disease: str,
    kg: KnowledgePump,
    synonym_map: Dict[str, List[str]],
    max_depth: int = 3,
) -> Dict[str, Any]:
    pass
    
    name_variants_b = [bacteria, bacteria.lower(), bacteria.lower().replace(" ", "_")]
    name_variants_m = [metabolite, metabolite.lower(), metabolite.lower().replace(" ", "_"),
                       metabolite.lower().replace("-", "_").replace(" ", "_")]

    paths = []
    for bname in name_variants_b:
        for mname in name_variants_m:
            paths = kg.find_relevant_paths(bname, mname, max_depth=max_depth)
            if paths:
                break
        if paths:
            break

    if not paths:
        
        pairwise = _compute_pairwise_counts(
            bacteria, metabolite, disease, synonym_map)
        agg_count = _aggregate_chain_count(pairwise)
        
        best_query = build_pubmed_query([bacteria, metabolite], synonym_map)

        return {
            'chain_path': [],
            'chain_count': agg_count,
            'chain_query': best_query,
            'all_paths': [],
            'has_path': False,
            'pairwise_counts': pairwise,
        }

    all_paths_info = []
    best_path = None
    best_count = -1
    best_pairwise = {}

    for path_tuples in paths:
        
        node_ids = []
        for src, rel, tgt in path_tuples:
            if src not in node_ids:
                node_ids.append(src)
            if tgt not in node_ids:
                node_ids.append(tgt)

        
        node_labels = [_kg_id_to_pubmed_term(nid, bacteria, metabolite) for nid in node_ids]

        
        pairwise = _compute_pairwise_counts(
            bacteria, metabolite, disease, synonym_map,
            path_node_labels=node_labels)
        agg_count = _aggregate_chain_count(pairwise)

        
        query_terms = node_labels + [disease]
        query = build_pubmed_query(query_terms, synonym_map)

        path_str = " -> ".join(node_labels)
        all_paths_info.append({
            'path': path_str,
            'node_labels': node_labels,
            'chain_count': agg_count,
            'pairwise_counts': pairwise,
            'query': query,
        })

        if agg_count > best_count:
            best_count = agg_count
            best_pairwise = pairwise
            best_path = {
                'chain_path': node_labels,
                'chain_path_ids': node_ids,
                'chain_count': agg_count,
                'chain_query': query,
                'path_tuples': path_tuples,
            }

    return {
        'chain_path': best_path['chain_path'] if best_path else [],
        'chain_path_ids': best_path.get('chain_path_ids', []) if best_path else [],
        'chain_count': best_count if best_count >= 0 else 0,
        'chain_query': best_path['chain_query'] if best_path else '',
        'path_tuples': best_path.get('path_tuples', []) if best_path else [],
        'all_paths': all_paths_info,
        'has_path': True,
        'pairwise_counts': best_pairwise,
    }


def compute_edge_counts(
    path_tuples: List[Any],
    kg: KnowledgePump,
    synonym_map: Dict[str, List[str]],
    bacteria_orig: str = "",
    metabolite_orig: str = "",
) -> List[EdgeCooccurrence]:
    pass
    results = []
    for src, rel, tgt in path_tuples:
        src_label = _kg_id_to_pubmed_term(src, bacteria_orig, metabolite_orig)
        tgt_label = _kg_id_to_pubmed_term(tgt, bacteria_orig, metabolite_orig)
        query = build_pubmed_query([src_label, tgt_label], synonym_map)
        count = query_pubmed_count(query)
        results.append(EdgeCooccurrence(
            source=src_label,
            target=tgt_label,
            relation=rel,
            cooccurrence=count,
            query=query,
        ))
    return results


def normalize_novelty(chain_count: int, c_max: int) -> float:
    pass
    if c_max <= 0:
        return 1.0
    return 1.0 - math.log(1 + chain_count) / math.log(1 + c_max)





def run_step2(
    candidates_path: str,
    gml_path: str,
    output_path: str,
    disease: str = DEFAULT_DISEASE,
    max_depth: int = 3,
    synonym_map_path: Optional[str] = None,
) -> list:
    pass
    print("=" * 60)
    print("  STEP 2: Chain Novelty Scoring")
    print("=" * 60)

    
    with open(candidates_path, 'r', encoding='utf-8') as f:
        candidates = json.load(f)

    kg = KnowledgePump(gml_path)

    
    synonym_map: Dict[str, List[str]] = {}
    if synonym_map_path:
        try:
            with open(synonym_map_path, 'r', encoding='utf-8') as f:
                custom_synonyms = json.load(f)
            synonym_map.update(custom_synonyms)
            print(f"Loaded custom synonyms: {len(custom_synonyms)} entries")
        except Exception as e:
            print(f"  [WARN] Could not load synonym map: {e}")
    print(f"  SapBERT synonym expansion: {'enabled' if HAS_SAPBERT else 'disabled'}")

    if not HAS_ENTREZ:
        raise RuntimeError(
            "Biopython is required for PubMed queries. "
            "Install with: pip install biopython")

    
    print(f"\nPhase 1: Finding KG paths and chain co-occurrence for {len(candidates)} candidates...")
    results: List[Dict[str, Any]] = []

    for i, cand in enumerate(candidates):
        bacteria = cand['bacteria']
        metabolite = cand['metabolite']

        chain_info = find_best_chain(bacteria, metabolite, disease, kg, synonym_map, max_depth)

        
        edge_coocs = []
        bottleneck = None
        if chain_info['has_path'] and chain_info.get('path_tuples'):
            edge_coocs = compute_edge_counts(
                chain_info['path_tuples'], kg, synonym_map,
                bacteria_orig=bacteria, metabolite_orig=metabolite,
            )

            
            if edge_coocs:
                bottleneck = min(edge_coocs, key=lambda e: e.cooccurrence)

        result = {
            'candidate': cand,
            'bacteria': bacteria,
            'metabolite': metabolite,
            'chain_path': chain_info['chain_path'],
            'chain_path_str': ' -> '.join(chain_info['chain_path']),
            'disease': disease,
            'query_terms': chain_info['chain_path'] + [disease] if chain_info['chain_path'] else [],
            'has_path': chain_info['has_path'],
            'chain_count': chain_info['chain_count'],
            'chain_novelty': 1.0,  
            'chain_query': chain_info['chain_query'],
            'pairwise_counts': chain_info.get('pairwise_counts', {}),
            'edge_cooccurrences': [asdict(e) for e in edge_coocs],
            'bottleneck_edge': asdict(bottleneck) if bottleneck else None,
            'all_paths_info': chain_info['all_paths'],
        }
        results.append(result)

        if (i + 1) % 50 == 0:
            has_path_n = sum(1 for r in results if r['has_path'])
            print(f"  Processed {i + 1}/{len(candidates)} candidates ({has_path_n} with KG paths)")

    _save_cache()

    
    print(f"\nPhase 2: Normalizing Chain Novelty...")
    all_chain_counts = [r['chain_count'] for r in results]
    c_max = max(all_chain_counts) if all_chain_counts else 0
    print(f"  C_max = {c_max} (max chain co-occurrence across all candidates)")

    for r in results:
        r['chain_novelty'] = round(normalize_novelty(r['chain_count'], c_max), 4)

    
    has_path_count = sum(1 for r in results if r['has_path'])
    dark_matter_count = sum(1 for r in results if r['chain_count'] == 0)
    print(f"\nResults:")
    print(f"  {has_path_count}/{len(results)} candidates have KG paths")
    print(f"  {dark_matter_count}/{len(results)} candidates have chain_count=0 (dark matter)")
    if c_max > 0:
        print(f"  Chain Novelty range: "
              f"{min(r['chain_novelty'] for r in results):.4f} - "
              f"{max(r['chain_novelty'] for r in results):.4f}")

    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(results)} scored candidates to {output_path}")
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Step 2: Chain Novelty Scoring')
    parser.add_argument('--candidates', default='outputs/step1_candidates.json')
    parser.add_argument('--gml',
                        default=str(Path(__file__).parent.parent / 'data' / 'knowledge_graph' / 'ibd_test_kg.gml'))
    parser.add_argument('--output', default='outputs/step2_chain_novelty.json')
    parser.add_argument('--disease', default='IBD')
    parser.add_argument('--max-depth', type=int, default=3)
    parser.add_argument('--synonym-map', default=None,
                        help='Path to custom synonym_map.json')
    args = parser.parse_args()

    run_step2(
        args.candidates, args.gml, args.output,
        disease=args.disease, max_depth=args.max_depth,
        synonym_map_path=args.synonym_map,
    )
