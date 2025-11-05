from __future__ import annotations
import json, re
from typing import List, Dict, Optional

def load_humaneval_jsonl(path: str, limit: Optional[int] = None) -> List[Dict]:
    """Load HumanEval-style tasks from a JSONL file."""
    items: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
            if limit is not None and len(items) >= limit:
                break
    # normalize entry_point if missing
    for p in items:
        if "entry_point" not in p or not p["entry_point"]:
            p["entry_point"] = sniff_entry_point(p.get("prompt", ""))
    return items

def sniff_entry_point(prompt: str) -> str:
    """Naively extract function name from `def name(...):`."""
    m = re.search(r"def\s+([a-zA-Z_]\w*)\s*\(", prompt)
    return m.group(1) if m else "solve"
