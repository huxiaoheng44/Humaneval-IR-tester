# src/humaneval_runner/codegen_from_plan.py
from __future__ import annotations
from typing import List, Dict, Optional
import os, re
from openai import OpenAI
from .plans import Plan, PlanFormat

def _require_key():
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY not set")


FORMAT_HINT = {
    PlanFormat.NL: (
        "Interpret the numbered natural-language steps as exact actions. "
        "Translate each action into Python statements using the same parameter names. "
        "Make conditionals explicit (if/else). Keep helpers local."
    ),
    PlanFormat.YAML: (
        "YAML has keys: io (inputs/outputs), steps (list of short actions), edges (edge cases). "
        "Implement the algorithm STRICTLY by following `steps`, translating each item to Python code. "
        "Use real Python operations implied by the text (e.g., filtering with str.isalnum, lower(), slicing for reverse). "
        "Honor edge cases when they affect control flow (e.g., 'empty string → None')."
    ),
    PlanFormat.DSL: (
        "The plan is a single STRUCTURED_PLAN{...} block. Semantics:\n"
        "- NODE<ID>: single operation (e.g., SET x = expr)\n"
        "- BRANCH<ID>: IF <cond> THEN GOTO <NODE/RETURN_ID> ELSE GOTO <NODE/RETURN_ID>\n"
        "- LOOP<ID>: FOR <var> IN <expr>: GOTO <NODE_ID>\n"
        "- RETURN<ID>: RETURN <expr>\n"
        "All control flow is explicit via GOTO/RETURN. Implement EXACTLY this flow using Python if/else, for-loops, "
        "assignments, and returns. Helpers may be local functions if needed."
    ),
    PlanFormat.MERMAID: (
        "Treat each node label as a short action and execute them in the given flow order. "
        "Translate nodes to Python statements; implement decision nodes as if/else; "
        "finish with the final return node."
    ),
}

SYSTEM = (
    "You are a precise Python coding assistant. Given ONLY a high-level PLAN, "
    "produce a single, self-contained Python solution that:\n"
    "- defines exactly the required function with the specified name/signature from the HumanEval prompt,\n"
    "- uses only the Python standard library,\n"
    "- avoids any file/network/IO, randomness, or global side effects,\n"
    "- is deterministic.\n"
    "Return ONLY raw Python code (no markdown fences, no commentary)."
)

REPAIR_SYSTEM = (
    "You are a Python debugging assistant. You will receive:\n"
    "- the exact function signature + docstring (contract),\n"
    "- a high-level PLAN that must be respected,\n"
    "- a CURRENT (failing) implementation of the function,\n"
    "- test failure information (traceback/assertion message).\n"
    "Task: produce a corrected implementation that fixes the failure while preserving the signature, "
    "keeping the solution deterministic and only using the standard library.\n"
    "Return ONLY raw Python code (no markdown, no explanations)."
)

def _best_code_from_text(text: str, entry_point: str) -> str:
    """Extract raw Python code from model output with priority on the block that defines the entry point."""
    if not text:
        return ""
    parts = re.split(r"```+", text)
    if len(parts) >= 3:
        candidates = []
        for i in range(1, len(parts), 2):
            block = parts[i]
            if block.lower().startswith("python"):
                block = block.split("\n", 1)[-1]
            candidates.append(block)
        for block in candidates:
            if re.search(rf"def\s+{re.escape(entry_point)}\s*\(", block):
                return block.strip()
        return max(candidates, key=len).strip()
    return text.replace("`", "").strip()

def generate_code_from_plan(
    entry_point: str,
    original_prompt: str,
    plan: Plan,
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    _require_key()
    client = OpenAI()
    hint = FORMAT_HINT[plan.format]

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                "Follow these constraints strictly:\n"
                f"- Entry point (function to implement): {entry_point}\n"
                "- Do not change the function name.\n"
                "- Do not add top-level prints or I/O.\n"
                "- If helpers are used, define them locally in this file."
            ),
        },
        {
            "role": "user",
            "content": (
                "HumanEval function signature and docstring (use as the exact contract):\n"
                f"```\n{original_prompt}\n```"
            ),
        },
        {
            "role": "user",
            "content": (
                f"PLAN format = {plan.format.value}.\n"
                f"Guidance for translation:\n{hint}\n\n"
                "PLAN (implement EXACTLY this algorithm):\n"
                f"{plan.content}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _best_code_from_text(raw, entry_point)

def _extract_assert_context(logs: str, window: int = 3) -> str:
    """
    从完整 traceback 里，抓取包含 'AssertionError' 或 'assert ' 的行附近的上下文，便于模型定位问题。
    """
    if not logs:
        return ""
    lines = logs.splitlines()
    hits = []
    for i, ln in enumerate(lines):
        if "AssertionError" in ln or ln.strip().startswith("assert "):
            start = max(0, i - window)
            end = min(len(lines), i + window + 1)
            hits.append("\n".join(lines[start:end]))
    return "\n\n---\n\n".join(hits)


def repair_code_with_feedback(
    entry_point: str,
    original_prompt: str,
    plan: Plan,
    bad_code: str,
    failure_logs: str,
    *,
    test_code: str = "",                 
    error_type: Optional[str] = None,    
    error_message: Optional[str] = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    max_tokens: int = 1200,
) -> str:
    """
    基于：函数契约 + 计划 + 失败实现 + 完整失败日志 (+ 官方测试)，产出修正后的代码。
    """
    _require_key()
    client = OpenAI()
    hint = FORMAT_HINT[plan.format]
    assert_ctx = _extract_assert_context(failure_logs)
    err_hdr = ""
    if error_type or error_message:
        err_hdr = f"Error: {error_type or ''} {error_message or ''}".strip()

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": REPAIR_SYSTEM},
        {
            "role": "user",
            "content": (
                "Constraints:\n"
                f"- Entry point (function to implement): {entry_point}\n"
                "- Keep the exact function name and signature.\n"
                "- Use only Python standard library.\n"
                "- No top-level I/O.\n"
            ),
        },
        {"role": "user", "content": "Function signature and docstring:\n" + f"```\n{original_prompt}\n```"},
        {
            "role": "user",
            "content": (
                f"PLAN format = {plan.format.value}.\n"
                f"Guidance for translation:\n{hint}\n\n"
                "PLAN (must be respected):\n"
                f"{plan.content}"
            ),
        },
        {"role": "user", "content": "Current failing implementation:\n" + f"```python\n{bad_code}\n```"},
        {"role": "user", "content": "Full failing logs:\n" + f"```\n{failure_logs}\n```"},
        {
            "role": "user",
            "content": "Failing assertion context (closest lines):\n" + (assert_ctx or "(not found)"),
        },
        # 只有当你传入 test_code 时才附上，避免无意义的空块
        *(
            [{"role": "user", "content": "Official tests:\n" + f"```\n{test_code}\n```"}]
            if test_code else []
        ),
        {
            "role": "user",
            "content": (
                "Apply the minimal necessary changes to fix the failure. "
                "Do not rewrite unrelated parts. "
                "Return ONLY the full corrected Python code."
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _best_code_from_text(raw, entry_point)