
from typing import Optional, List, Dict, Any
from pathlib import Path

from knowledge_pump import get_knowledge_pump, KnowledgePump


class KnowledgeFormatter:
    pass
    
    def __init__(self, knowledge_pump: Optional[KnowledgePump] = None):
        pass
        self.pump = knowledge_pump or get_knowledge_pump()
    
    def format_fella_pathways(
        self, 
        fella_result: Optional[Dict[str, Any]],
        max_pathways: int = 5,
        max_enzymes: int = 3
    ) -> str:
        pass
        if not fella_result or fella_result.get('status') == 'error':
            return "No pathway enrichment data available."
        
        parts = []
        
        
        pathways = fella_result.get('enriched_pathways', [])
        if pathways:
            parts.append("**Enriched Metabolic Pathways:**")
            for i, p in enumerate(pathways[:max_pathways]):
                name = p.get('name', p.get('id', 'Unknown'))
                p_val = p.get('p_value', p.get('pvalue', 'N/A'))
                if isinstance(p_val, float):
                    p_val = f"{p_val:.4f}"
                kegg_id = p.get('id', '')
                parts.append(f"  {i+1}. {name} (KEGG: {kegg_id}, p={p_val})")
        
        
        enzymes = fella_result.get('enriched_enzymes', [])
        if enzymes:
            parts.append("\n**Key Enzymes:**")
            for e in enzymes[:max_enzymes]:
                name = e.get('name', e.get('id', 'Unknown'))
                ec = e.get('id', '')
                parts.append(f"  - {name} (EC: {ec})")
        
        
        metabolites = fella_result.get('input_metabolites', [])
        if metabolites:
            parts.append(f"\n**Input Metabolites:** {', '.join(metabolites[:10])}")
        
        if not parts:
            return "No significant pathway enrichment found."
        
        return "\n".join(parts)
    
    def format_correlation_evidence(
        self,
        correlation: float,
        p_value: float,
        bacteria: str,
        metabolite: str
    ) -> str:
        pass
        
        abs_cor = abs(correlation)
        if abs_cor > 0.7:
            strength = "strong"
        elif abs_cor > 0.5:
            strength = "moderate-to-strong"
        elif abs_cor > 0.3:
            strength = "moderate"
        else:
            strength = "weak"
        
        direction = "positive" if correlation > 0 else "negative"
        
        
        if p_value < 0.001:
            sig = "highly significant (p < 0.001)"
        elif p_value < 0.01:
            sig = "significant (p < 0.01)"
        elif p_value < 0.05:
            sig = "marginally significant (p < 0.05)"
        else:
            sig = f"not significant (p = {p_value:.4f})"
        
        return (
            f"**MMSage Correlation Evidence:**\n"
            f"MMSage trajectory analysis reveals a {strength} {direction} correlation "
            f"(r = {correlation:.3f}) between {bacteria.replace('_', ' ')} and {metabolite}. "
            f"This association is {sig}."
        )
    
    def build_mechanism_context(
        self,
        bacteria: str,
        metabolite: str,
        correlation: Optional[float] = None,
        p_value: Optional[float] = None,
        fella_result: Optional[Dict[str, Any]] = None,
        max_chars: int = 6000
    ) -> str:
        pass
        sections = []
        
        
        sections.append("# Mechanism Reasoning Task\n")
        sections.append(
            f"Analyze the mechanistic relationship between **{bacteria.replace('_', ' ')}** "
            f"and **{metabolite}** based on the following evidence.\n"
        )
        
        
        if correlation is not None and p_value is not None:
            sections.append("## Correlation Evidence\n")
            sections.append(self.format_correlation_evidence(
                correlation, p_value, bacteria, metabolite
            ))
            sections.append("")
        
        
        sections.append("## Prior Knowledge\n")
        gml_context = self.pump.build_llm_context(bacteria, metabolite, max_chars=2500)
        sections.append(gml_context)
        sections.append("")
        
        
        if fella_result:
            sections.append("## Metabolic Pathway Evidence\n")
            sections.append(self.format_fella_pathways(fella_result))
            sections.append("")
        
        
        sections.append("## Requested Analysis\n")
        sections.append(
            "Based on the above evidence, provide:\n"
            "1. The most likely causal direction (microbe → metabolite or metabolite → microbe)\n"
            "2. A proposed molecular mechanism explaining this association\n"
            "3. Key supporting evidence from the provided context\n"
            "4. Confidence level and limitations of this hypothesis"
        )
        
        
        context = "\n".join(sections)
        if len(context) > max_chars:
            context = context[:max_chars - 100] + "\n\n[Context truncated...]"
        
        return context
    
    def build_causal_context(
        self,
        bacteria: str,
        metabolite: str,
        correlation: float,
        p_value: float
    ) -> str:
        pass
        sections = []
        
        
        sections.append(
            f"Determine the causal direction between {bacteria.replace('_', ' ')} "
            f"and {metabolite}.\n"
        )
        
        
        sections.append(self.format_correlation_evidence(
            correlation, p_value, bacteria, metabolite
        ))
        sections.append("")
        
        
        sections.append("**Prior Knowledge:**")
        
        
        microbe_id = self.pump._resolve_entity(bacteria, 'microbe')
        if microbe_id:
            node = self.pump.get_node(microbe_id)
            if node:
                sections.append(f"- {node.get('label', bacteria)}: {node.get('description', '')[:300]}")
        
        
        metabolite_id = self.pump._resolve_entity(metabolite, 'metabolite')
        if microbe_id and metabolite_id:
            edge = self.pump.get_edge(microbe_id, metabolite_id)
            if edge:
                sections.append(f"- Known relation: {edge.get('relation', 'associated')} "
                              f"(confidence: {edge.get('confidence', 'unknown')})")
        
        return "\n".join(sections)
    
    def extract_key_facts(
        self,
        bacteria: str,
        metabolite: str
    ) -> Dict[str, Any]:
        pass
        facts = {
            'bacteria': {
                'name': bacteria,
                'label': bacteria.replace('_', ' '),
                'description': None,
                'type': 'microbe'
            },
            'metabolite': {
                'name': metabolite,
                'label': metabolite,
                'description': None,
                'kegg_id': None,
                'type': 'metabolite'
            },
            'relation': {
                'exists': False,
                'type': None,
                'description': None,
                'confidence': None,
                'pmid': None
            },
            'pathways': []
        }
        
        
        microbe_id = self.pump._resolve_entity(bacteria, 'microbe')
        if microbe_id:
            node = self.pump.get_node(microbe_id)
            if node:
                facts['bacteria']['description'] = node.get('description')
                facts['bacteria']['label'] = node.get('label', bacteria)
        
        
        metabolite_id = self.pump._resolve_entity(metabolite, 'metabolite')
        if metabolite_id:
            node = self.pump.get_node(metabolite_id)
            if node:
                facts['metabolite']['description'] = node.get('description')
                facts['metabolite']['label'] = node.get('label', metabolite)
                facts['metabolite']['kegg_id'] = node.get('kegg_id')
        
        
        if microbe_id and metabolite_id:
            edge = self.pump.get_edge(microbe_id, metabolite_id)
            if edge:
                facts['relation'] = {
                    'exists': True,
                    'type': edge.get('relation'),
                    'description': edge.get('description'),
                    'confidence': edge.get('confidence'),
                    'pmid': edge.get('pmid')
                }
        
        
        if metabolite_id:
            for neighbor in self.pump.get_neighbors(metabolite_id, direction='out'):
                if neighbor.get('type') == 'pathway':
                    facts['pathways'].append({
                        'id': neighbor['id'],
                        'name': neighbor.get('label'),
                        'kegg_id': neighbor.get('kegg_id')
                    })
        
        return facts



_formatter: Optional[KnowledgeFormatter] = None


def get_knowledge_formatter() -> KnowledgeFormatter:
    pass
    global _formatter
    if _formatter is None:
        _formatter = KnowledgeFormatter()
    return _formatter


if __name__ == "__main__":
    
    formatter = KnowledgeFormatter()
    
    print("=== Mechanism Context ===")
    context = formatter.build_mechanism_context(
        bacteria="Akkermansia_muciniphila",
        metabolite="Isobutyric acid",
        correlation=0.65,
        p_value=0.001,
        fella_result={
            'status': 'success',
            'enriched_pathways': [
                {'id': 'hsa00280', 'name': 'BCAA degradation', 'p_value': 0.001},
                {'id': 'hsa00650', 'name': 'Butanoate metabolism', 'p_value': 0.005}
            ],
            'enriched_enzymes': [
                {'id': '1.2.1.27', 'name': 'MMSDH'}
            ]
        }
    )
    print(context)
    print()
    
    print("=== Key Facts ===")
    facts = formatter.extract_key_facts(
        "Akkermansia_muciniphila",
        "Propionate"
    )
    import json
    print(json.dumps(facts, indent=2))
