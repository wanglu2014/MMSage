
import os
import networkx as nx
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple



BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_GML_PATH = Path(os.getenv("PRIOR_KG_PATH", str(DATA_DIR / "prior_knowledge.gml")))


class KnowledgePump:
    pass
    
    def __init__(self, gml_path: Optional[str] = None):
        pass
        self.gml_path = Path(gml_path) if gml_path else DEFAULT_GML_PATH
        self.graph: Optional[nx.DiGraph] = None
        self._load_graph()
    
    def _load_graph(self) -> None:
        pass
        if not self.gml_path.exists():
            raise FileNotFoundError(f"GML file not found at {self.gml_path}")
        
        try:
            self.graph = nx.read_gml(str(self.gml_path))
            print(f"Loaded knowledge graph: {self.graph.number_of_nodes()} nodes, "
                  f"{self.graph.number_of_edges()} edges")
        except Exception as e:
            raise RuntimeError(f"Error loading GML file: {e}") from e
    
    def reload(self, gml_path: Optional[str] = None) -> bool:
        pass
        if gml_path:
            self.gml_path = Path(gml_path)
        
        try:
            self._load_graph()
            return self.graph is not None and self.graph.number_of_nodes() > 0
        except Exception:
            return False
    
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        pass
        if self.graph is None or node_id not in self.graph:
            return None
        
        return dict(self.graph.nodes[node_id])
    
    def get_node_context(self, entity_id: str) -> str:
        pass
        node = self.get_node(entity_id)
        if not node:
            return f"No information found for entity: {entity_id}"
        
        parts = []
        label = node.get('label', entity_id)
        node_type = node.get('type', 'unknown')
        description = node.get('description', 'No description available.')
        
        parts.append(f"**{label}** ({node_type})")
        parts.append(description)
        
        
        if 'kegg_id' in node:
            parts.append(f"KEGG ID: {node['kegg_id']}")
        
        return "\n".join(parts)
    
    def get_edge(self, source: str, target: str) -> Optional[Dict[str, Any]]:
        pass
        if self.graph is None or not self.graph.has_edge(source, target):
            return None

        
        if isinstance(self.graph, (nx.MultiDiGraph, nx.MultiGraph)):
            
            keys = list(self.graph[source][target].keys())
            if keys:
                return dict(self.graph[source][target][keys[0]])
            return None

        return dict(self.graph.edges[source, target])
    
    def get_relation_context(self, source: str, target: str) -> str:
        pass
        edge = self.get_edge(source, target)
        if not edge:
            return f"No direct relation found between {source} and {target}"
        
        parts = []
        relation = edge.get('relation', 'related_to')
        description = edge.get('description', 'No description available.')
        
        
        source_node = self.get_node(source)
        target_node = self.get_node(target)
        source_label = source_node.get('label', source) if source_node else source
        target_label = target_node.get('label', target) if target_node else target
        
        parts.append(f"{source_label} --[{relation}]--> {target_label}")
        parts.append(description)
        
        
        if 'pmid' in edge:
            parts.append(f"Literature: PMID {edge['pmid']}")
        if 'confidence' in edge:
            parts.append(f"Confidence: {edge['confidence']}")
        
        return "\n".join(parts)
    
    def find_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        pass
        if self.graph is None:
            return []
        
        results = []
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get('type') == node_type:
                results.append({'id': node_id, **attrs})
        
        return results
    
    def find_node_by_label(self, label: str, fuzzy: bool = True) -> Optional[str]:
        pass
        if self.graph is None:
            return None
        
        label_lower = label.lower().replace(' ', '_').replace('.', '')
        
        for node_id, attrs in self.graph.nodes(data=True):
            node_label = attrs.get('label', '').lower().replace(' ', '_').replace('.', '')
            if fuzzy:
                if label_lower in node_label or node_label in label_lower:
                    return node_id
            else:
                if label_lower == node_label:
                    return node_id
        
        return None
    
    def get_neighbors(self, node_id: str, direction: str = 'both') -> List[Dict[str, Any]]:
        pass
        if self.graph is None or node_id not in self.graph:
            return []
        
        neighbors = []
        
        if direction in ('out', 'both'):
            for target in self.graph.successors(node_id):
                edge_data = self.get_edge(node_id, target)
                node_data = self.get_node(target)
                neighbors.append({
                    'id': target,
                    'direction': 'out',
                    'relation': edge_data.get('relation') if edge_data else 'unknown',
                    **node_data
                })
        
        if direction in ('in', 'both'):
            for source in self.graph.predecessors(node_id):
                edge_data = self.get_edge(source, node_id)
                node_data = self.get_node(source)
                neighbors.append({
                    'id': source,
                    'direction': 'in',
                    'relation': edge_data.get('relation') if edge_data else 'unknown',
                    **node_data
                })
        
        return neighbors
    
    def find_relevant_paths(
        self, 
        microbe: str, 
        metabolite: str, 
        max_depth: int = 3
    ) -> List[List[Tuple[str, str, str]]]:
        pass
        if self.graph is None:
            return []
        
        
        microbe_id = self._resolve_entity(microbe, 'microbe')
        metabolite_id = self._resolve_entity(metabolite, 'metabolite')
        
        if not microbe_id or not metabolite_id:
            return []
        
        paths = []
        
        try:
            
            for path in nx.all_simple_paths(
                self.graph, 
                source=microbe_id, 
                target=metabolite_id, 
                cutoff=max_depth
            ):
                path_with_relations = []
                for i in range(len(path) - 1):
                    edge = self.get_edge(path[i], path[i + 1])
                    relation = edge.get('relation', 'related_to') if edge else 'related_to'
                    path_with_relations.append((path[i], relation, path[i + 1]))
                paths.append(path_with_relations)
        except nx.NetworkXNoPath:
            pass
        
        
        try:
            for path in nx.all_simple_paths(
                self.graph, 
                source=metabolite_id, 
                target=microbe_id, 
                cutoff=max_depth
            ):
                path_with_relations = []
                for i in range(len(path) - 1):
                    edge = self.get_edge(path[i], path[i + 1])
                    relation = edge.get('relation', 'related_to') if edge else 'related_to'
                    path_with_relations.append((path[i], relation, path[i + 1]))
                paths.append(path_with_relations)
        except nx.NetworkXNoPath:
            pass
        
        return paths
    
    def _resolve_entity(self, name: str, expected_type: Optional[str] = None) -> Optional[str]:
        pass
        
        if self.graph is not None and name in self.graph:
            return name
        
        
        node_id = self.find_node_by_label(name)
        if node_id:
            if expected_type:
                node = self.get_node(node_id)
                if node and node.get('type') == expected_type:
                    return node_id
            else:
                return node_id
        
        
        if expected_type:
            candidate_id = f"{expected_type}_{name.lower().replace(' ', '_')}"
            if self.graph is not None and candidate_id in self.graph:
                return candidate_id
        
        return None
    
    def build_llm_context(
        self, 
        microbe: str, 
        metabolite: str,
        max_chars: int = 4000
    ) -> str:
        pass
        parts = []
        
        
        microbe_id = self._resolve_entity(microbe, 'microbe')
        metabolite_id = self._resolve_entity(metabolite, 'metabolite')
        
        
        parts.append("## Prior Knowledge Context\n")
        
        
        parts.append("### Microbe Information")
        if microbe_id:
            parts.append(self.get_node_context(microbe_id))
        else:
            parts.append(f"No prior knowledge available for: {microbe}")
        parts.append("")
        
        
        parts.append("### Metabolite Information")
        if metabolite_id:
            parts.append(self.get_node_context(metabolite_id))
        else:
            parts.append(f"No prior knowledge available for: {metabolite}")
        parts.append("")
        
        
        parts.append("### Known Relations")
        if microbe_id and metabolite_id:
            
            direct_context = self.get_relation_context(microbe_id, metabolite_id)
            if "No direct relation" not in direct_context:
                parts.append(direct_context)
            
            
            reverse_context = self.get_relation_context(metabolite_id, microbe_id)
            if "No direct relation" not in reverse_context:
                parts.append(reverse_context)
        
        
        if microbe_id and metabolite_id:
            paths = self.find_relevant_paths(microbe, metabolite, max_depth=3)
            if paths:
                parts.append("\n### Knowledge Paths")
                for i, path in enumerate(paths[:3]):  
                    path_str = " → ".join([
                        f"{self._get_label(s)} --[{r}]-- {self._get_label(t)}"
                        for s, r, t in path
                    ])
                    parts.append(f"Path {i + 1}: {path_str}")
        parts.append("")
        
        
        parts.append("### Related Pathways")
        pathways_found = False
        if metabolite_id:
            for neighbor in self.get_neighbors(metabolite_id, direction='out'):
                if neighbor.get('type') == 'pathway':
                    parts.append(f"- {neighbor.get('label', neighbor['id'])}: "
                               f"{neighbor.get('description', '')[:200]}")
                    pathways_found = True
        if not pathways_found:
            parts.append("No pathway information in knowledge graph.")
        
        
        context = "\n".join(parts)
        if len(context) > max_chars:
            context = context[:max_chars - 100] + "\n\n[Context truncated...]"
        
        return context
    
    def _get_label(self, node_id: str) -> str:
        pass
        node = self.get_node(node_id)
        if node:
            return node.get('label', node_id)
        return node_id
    
    def get_graph_stats(self) -> Dict[str, Any]:
        pass
        if self.graph is None:
            return {'status': 'not_loaded'}
        
        node_types = {}
        for _, attrs in self.graph.nodes(data=True):
            t = attrs.get('type', 'unknown')
            node_types[t] = node_types.get(t, 0) + 1
        
        relation_types = {}
        for _, _, attrs in self.graph.edges(data=True):
            r = attrs.get('relation', 'unknown')
            relation_types[r] = relation_types.get(r, 0) + 1
        
        return {
            'status': 'loaded',
            'gml_path': str(self.gml_path),
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'node_types': node_types,
            'relation_types': relation_types
        }



_knowledge_pump: Optional[KnowledgePump] = None


def get_knowledge_pump(gml_path: Optional[str] = None) -> KnowledgePump:
    pass
    global _knowledge_pump
    if _knowledge_pump is None:
        _knowledge_pump = KnowledgePump(gml_path)
    elif gml_path:
        _knowledge_pump.reload(gml_path)
    return _knowledge_pump


if __name__ == "__main__":
    
    pump = KnowledgePump()
    
    print("=== Graph Stats ===")
    stats = pump.get_graph_stats()
    print(f"Nodes: {stats.get('total_nodes')}")
    print(f"Edges: {stats.get('total_edges')}")
    print(f"Node types: {stats.get('node_types')}")
    print()
    
    print("=== Microbe Context ===")
    print(pump.get_node_context("microbe_akkermansia"))
    print()
    
    print("=== Relation Context ===")
    print(pump.get_relation_context("microbe_akkermansia", "metabolite_propionate"))
    print()
    
    print("=== Find Paths ===")
    paths = pump.find_relevant_paths("Akkermansia", "Butyrate", max_depth=3)
    for i, path in enumerate(paths):
        print(f"Path {i + 1}: {path}")
    print()
    
    print("=== LLM Context ===")
    context = pump.build_llm_context("Akkermansia muciniphila", "Isobutyric acid")
    print(context)
