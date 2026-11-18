















from dataclasses import dataclass, field, asdict  
from typing import Dict, List  


@dataclass
class HopEvidence:


    hop_type: str           
    pubmed_count: int       

    db_hits: Dict[str, bool] = field(default_factory=dict)    
    db_details: Dict[str, dict] = field(default_factory=dict)  
    sources: List[str] = field(default_factory=list)           
    query_used: str = ""    

    def to_dict(self) -> dict:

        return asdict(self)
