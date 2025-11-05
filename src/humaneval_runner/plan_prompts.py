# src/humaneval_runner/plan_prompts.py
from __future__ import annotations
from typing import Dict, List, TypedDict
from .plans import PlanFormat

# —— Few-shot exemplars for each plan format —— #

class FewShot(TypedDict):
    task_id: str
    entry_point: str
    prompt: str       # HumanEval-style prompt (signature + docstring)
    plan: str         # Plan text in the target format

class PlanTemplate(TypedDict):
    system: str
    shots: List[FewShot]

TEMPLATES: Dict[PlanFormat, PlanTemplate] = {
    # ----------------------------
    # Natural language (tighter style; Python anchors; explicit returns)
    # ----------------------------
    PlanFormat.NL: {
        "system": (
            "You are a planning specialist. Given a HumanEval-style prompt, "
            "produce a numbered, minimal, purely natural-language PLAN for solving the task.\n"
            "Rules:\n"
            "- 5–8 steps, each a single action; keep each step short.\n"
            "- Use the exact parameter names from the signature.\n"
            "- Prefer real Python terms (len, lower, sorted, set, dict, Counter, hashlib.md5(...).hexdigest()).\n"
            "- Make conditionals explicit: IF <condition> THEN <action> ELSE <action>.\n"
            "- End with an explicit return description (e.g., 'return True', 'return the computed value').\n"
            "No code blocks or pseudo-code; only crisp action steps."
        ),
        "shots": [
            {
                "task_id": "NL/EX1",
                "entry_point": "is_palindrome",
                "prompt": (
                    "def is_palindrome(s: str) -> bool:\n"
                    "    \"\"\"Return True if s is a palindrome, ignoring case and non-alphanumerics.\"\"\"\n"
                ),
                "plan": (
                    "1. Remove all non-alphanumeric characters from s.\n"
                    "2. Convert the filtered string to lowercase.\n"
                    "3. Compute the reverse of the normalized string.\n"
                    "4. IF the normalized string equals its reverse THEN return True ELSE return False.\n"
                    "5. Edge cases: empty string or single character should return True."
                ),
            },
            {
                "task_id": "NL/EX2",
                "entry_point": "sum_unique",
                "prompt": (
                    "def sum_unique(nums: list[int]) -> int:\n"
                    "    \"\"\"Return the sum of elements that occur exactly once in nums.\"\"\"\n"
                ),
                "plan": (
                    "1. Build a frequency map for nums (e.g., using a counter/dictionary).\n"
                    "2. Identify values whose frequency equals 1.\n"
                    "3. Sum those unique values.\n"
                    "4. Return the sum.\n"
                    "5. Edge cases: empty list returns 0."
                ),
            },
        ],
    },

    # ----------------------------
    # YAML (keep original schema: io/steps/edges; make steps Python-anchored & explicit)
    # ----------------------------
    PlanFormat.YAML: {
        "system": (
            "You are a planning specialist. Output a VALID YAML object with keys:\n"
            "  - io: inputs/outputs\n"
            "  - steps: list of short, single-action instructions (use real Python terms)\n"
            "  - edges: list of edge cases\n"
            "Do NOT include code blocks or Markdown fences. Keep steps minimal and actionable."
        ),
        "shots": [
            {
                "task_id": "YAML/EX1",
                "entry_point": "is_palindrome",
                "prompt": (
                    "def is_palindrome(s: str) -> bool:\n"
                    "    \"\"\"Return True if s is a palindrome, ignoring case and non-alphanumerics.\"\"\"\n"
                ),
                "plan": (
                    "io:\n"
                    "  inputs: [s: str]\n"
                    "  outputs: [bool]\n"
                    "steps:\n"
                    "  - filter s to keep only alphanumeric characters\n"
                    "  - lowercase the filtered string\n"
                    "  - compute the reverse of the normalized string\n"
                    "  - if normalized equals its reverse then return True else return False\n"
                    "edges:\n"
                    "  - empty string → True\n"
                    "  - single char → True\n"
                ),
            },
            {
                "task_id": "YAML/EX2",
                "entry_point": "sum_unique",
                "prompt": (
                    "def sum_unique(nums: list[int]) -> int:\n"
                    "    \"\"\"Return the sum of elements that occur exactly once in nums.\"\"\"\n"
                ),
                "plan": (
                    "io:\n"
                    "  inputs: [nums: list[int]]\n"
                    "  outputs: [int]\n"
                    "steps:\n"
                    "  - build a frequency map of nums (e.g., counts)\n"
                    "  - identify values with count == 1\n"
                    "  - sum those unique values\n"
                    "  - return the sum\n"
                    "edges:\n"
                    "  - empty list → 0\n"
                ),
            },
        ],
    },

    # ----------------------------
    # DSL (your STRUCTURED_PLAN with NODE/BRANCH/LOOP/RETURN + explicit GOTO)
    # ----------------------------
    PlanFormat.DSL: {
        "system": (
            "You are a senior Python algorithm-planning assistant. "
            "Produce ONLY a structured control-flow plan in the DSL below, with no extra commentary or code.\n\n"
            "DSL SPEC (keywords uppercase):\n"
            "--------------------------------------------------------------------\n"
            "STRUCTURED_PLAN{\n"
            "  NODE<ID>: <single operation>\n"
            "  BRANCH<ID>: IF <condition> THEN GOTO <NODE/RETURN_ID> ELSE GOTO <NODE/RETURN_ID>\n"
            "  LOOP<ID>: FOR <var> IN <expr>: GOTO <NODE_ID>\n"
            "  RETURN<ID>: RETURN <expr>\n"
            "}\n"
            "All jumps must be explicit via GOTO or RETURN. "
            "Each branch must cover all outcomes. End every path with a RETURN statement.\n"
            "--------------------------------------------------------------------\n"
            "Output ONLY a single STRUCTURED_PLAN{...} block."
        ),
        "shots": [
            {
                "task_id": "DSL/EX1",
                "entry_point": "encrypt",
                "prompt": (
                    "def encrypt(s):\n"
                    "    \"\"\"\n"
                    "    Return an encrypted string where each character is shifted forward by 4 positions\n"
                    "    (alphabet rotation by 2 x 2).\n"
                    "    \"\"\"\n"
                ),
                "plan": (
                    "STRUCTURED_PLAN{\n"
                    "  BRANCH0: IF len(s) == 0 THEN GOTO RETURN_EMPTY ELSE GOTO NODE1\n"
                    "  NODE1: SET alpha = \"abcdefghijklmnopqrstuvwxyz\"\n"
                    "  NODE2: SET res = \"\"\n"
                    "  LOOP1: FOR ch IN s: GOTO BRANCH1\n\n"
                    "  BRANCH1: IF ch in alpha THEN GOTO NODE3 ELSE GOTO NODE4\n"
                    "  NODE3: SET idx = (index(alpha, ch) + 4) % 26\n"
                    "         SET res = res + alpha[idx]\n"
                    "         GOTO LOOP1\n"
                    "  NODE4: SET res = res + ch\n"
                    "         GOTO LOOP1\n\n"
                    "  RETURN_ENCRYPTED: RETURN res\n"
                    "  RETURN_EMPTY: RETURN \"\"\n"
                    "}"
                ),
            },
            {
                "task_id": "DSL/EX2",
                "entry_point": "check_if_last_char_is_a_letter",
                "prompt": (
                    "def check_if_last_char_is_a_letter(txt):\n"
                    "    \"\"\"\n"
                    "    Return True iff the last non-space character of txt is a standalone alphabetical\n"
                    "    letter (word length = 1).\n"
                    "    \"\"\"\n"
                ),
                "plan": (
                    "STRUCTURED_PLAN{\n"
                    "  NODE1: SET stripped = txt.rstrip()\n"
                    "  BRANCH1: IF len(stripped) == 0 THEN GOTO RETURN_FALSE ELSE GOTO NODE2\n\n"
                    "  NODE2: SET last = stripped[-1]\n"
                    "  BRANCH2: IF last not in \"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\" "
                    "THEN GOTO RETURN_FALSE ELSE GOTO NODE3\n\n"
                    "  NODE3: SET words = stripped.split()\n"
                    "  BRANCH3: IF len(words[-1]) == 1 THEN GOTO RETURN_TRUE ELSE GOTO RETURN_FALSE\n\n"
                    "  RETURN_TRUE: RETURN True\n"
                    "  RETURN_FALSE: RETURN False\n"
                    "}"
                ),
            },
        ],
    },

    # ----------------------------
    # Mermaid (keep minimal nodes; action-oriented, Python-ish wording)
    # ----------------------------
    PlanFormat.MERMAID: {
        "system": (
            "You are a planning specialist. Output ONLY a Mermaid flowchart (no fences).\n"
            "Use: flowchart TD\n"
            "Nodes must describe single actions using Python terms. Keep them short.\n"
            "Example syntax:\n"
            "flowchart TD\n"
            "N0[Step text]\n"
            "N0 --> N1\n"
            "...\n"
            "No code, no commentary."
        ),
        "shots": [
            {
                "task_id": "MM/EX1",
                "entry_point": "is_palindrome",
                "prompt": (
                    "def is_palindrome(s: str) -> bool:\n"
                    "    \"\"\"Return True if s is a palindrome, ignoring case and non-alphanumerics.\"\"\"\n"
                ),
                "plan": (
                    "flowchart TD\n"
                    "N0[filter to alphanumerics]\n"
                    "N1[to lowercase]\n"
                    "N2[compute reverse]\n"
                    "N3[if equal then return True else return False]\n"
                    "N0 --> N1\n"
                    "N1 --> N2\n"
                    "N2 --> N3\n"
                ),
            },
            {
                "task_id": "MM/EX2",
                "entry_point": "sum_unique",
                "prompt": (
                    "def sum_unique(nums: list[int]) -> int:\n"
                    "    \"\"\"Return the sum of elements that occur exactly once in nums.\"\"\"\n"
                ),
                "plan": (
                    "flowchart TD\n"
                    "A[build frequency map]\n"
                    "B[select values with count==1]\n"
                    "C[sum selected values]\n"
                    "D[return the sum]\n"
                    "A --> B\n"
                    "B --> C\n"
                    "C --> D\n"
                ),
            },
        ],
    },
}
