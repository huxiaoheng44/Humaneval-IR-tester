# src/humaneval_runner/planner_per_format.py
from __future__ import annotations
from typing import List, Dict, Optional
import os, re
from openai import OpenAI
from .plans import Plan, PlanFormat
from .plan_prompts import TEMPLATES

def _require_key():
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY not set")


def _messages_for_format(fmt: PlanFormat, entry_point: str, prompt: str) -> List[Dict[str, str]]:
    tpl = TEMPLATES[fmt]
    msgs: List[Dict[str, str]] = [{"role": "system", "content": tpl["system"]}]
    for shot in tpl["shots"]:
        msgs.append({
            "role": "user",
            "content": f"Entry point: {shot['entry_point']}\nTask:\n{shot['prompt']}"
        })
        msgs.append({"role": "assistant", "content": shot["plan"]})
    msgs.append({"role": "user", "content": f"Entry point: {entry_point}\nTask:\n{prompt}"})
    return msgs

def make_plan(entry_point: str, prompt: str, fmt: PlanFormat,
              model: str="gpt-4o-mini", temperature: float=0.2,
              max_tokens: int=800) -> Plan:
    _require_key()
    client = OpenAI()
    messages = _messages_for_format(fmt, entry_point, prompt)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = _strip_md_fences((resp.choices[0].message.content or "").strip())
    content = _extract_plan_block(fmt, content)  
    return Plan(fmt, content)

# ----------（Re-PLAN） ----------

def _replan_system_for_format(fmt: PlanFormat) -> str:
    if fmt == PlanFormat.DSL:
        return (
            "You are a Python algorithm planning assistant. "
            "Rewrite the plan in the SAME DSL (STRUCTURED_PLAN{...}) to fix failing cases indicated by logs and tests. "
            "Keep it minimal, explicit, and correct. Output ONLY one STRUCTURED_PLAN{...} block."
        )
    if fmt == PlanFormat.YAML:
        return (
            "You are a Python planning assistant. Rewrite the plan as a VALID YAML object with keys io/steps/edges, "
            "fixing the failing cases indicated by logs and tests. Use short actionable steps with real Python terms. "
            "Output ONLY YAML (no Markdown fences, no code)."
        )
    if fmt == PlanFormat.MERMAID:
        return (
            "Rewrite the plan as ONLY a Mermaid flowchart (flowchart TD), fixing failing cases from logs and tests. "
            "Use short action nodes. Output ONLY the flowchart (no fences, no commentary)."
        )
    # NL
    return (
        "Rewrite the plan as a numbered, concise natural-language plan (5–8 steps), "
        "fixing failing cases indicated by logs and tests. "
        "Use explicit IF/ELSE and explicit return conditions. Output ONLY the plan steps."
    )

def _strip_md_fences(text: str) -> str:
    parts = re.split(r"```+", text)
    if len(parts) >= 3:
        body = parts[1]
        if body.lower().startswith(("yaml", "python", "mermaid")):
            body = body.split("\n", 1)[-1]
        return body.strip()
    return text.replace("`", "").strip()

def _extract_plan_block(fmt: PlanFormat, text: str) -> str:
    """
    extract the main plan block from the text, based on format.
    """
    s = text.strip()
    if fmt == PlanFormat.DSL:
        m = re.search(r"STRUCTURED_PLAN\s*\{", s)
        if m:
            start = m.start()
            end = s.rfind("}")
            if end != -1 and end > start:
                return s[start:end+1].strip()
        return s
    if fmt == PlanFormat.MERMAID:
        m = re.search(r"(?:^|\n)\s*flowchart\s+TD", s)
        if m:
            return s[m.start():].strip()
        return s
    # YAML / NL return as-is
    return s

def _clip(text: str, max_chars: int = 6000) -> str:
    if not text:
        return ""
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n... [truncated] ..."
    return text



def _scan_balanced_parens(s: str, start_idx: int) -> int:
    """
    from start_idx (pointing to a '('), scan forward to find the matching ')'.
    """
    depth = 0
    i = start_idx
    in_single = False
    in_double = False
    while i < len(s):
        ch = s[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1

def _extract_failing_asserts(logs: str, max_cases: int = 6) -> List[Dict[str, str]]:
    """
    extract assert statements from logs, parse into structured cases if possible.
    """
    if not logs:
        return []
    cases: List[Dict[str, str]] = []

    op_pattern = re.compile(r"\s(==|!=|<=|>=|<|>|not\s+in|in)\s")

    for line in logs.splitlines():
        if len(cases) >= max_cases:
            break
        line = line.strip()
        if not line.startswith("assert"):
            continue


        expr = line[len("assert"):].strip()
        expr = re.sub(r',\s*([\'"]).*?\1\s*$', '', expr)

        m = op_pattern.search(expr)
        if not m:

            cases.append({"raw": expr})
            continue

        left = expr[:m.start()].strip()
        op = m.group(1)
        right = expr[m.end():].strip()


        if left.startswith("candidate("):
            start_args = left.find("(")
            end_args = _scan_balanced_parens(left, start_args)
            if end_args != -1:
                args_str = left[start_args + 1 : end_args].strip()

                expected = right

                cases.append({"input": args_str, "op": op, "expected": expected})
                continue

        cases.append({"raw": f"{left} {op} {right}"})

    return cases


def _format_failing_examples_msg(entry_point: str, cases: List[Dict[str, str]]) -> str:

    if not cases:
        return ""
    lines = ["Failing examples extracted from assertions (satisfy these without hardcoding outputs):"]
    for c in cases:
        if "input" in c:
            if c.get("op") == "!=":
                lines.append(f"- input: ({c['input']})")
                lines.append(f"  must_not_equal: {c['expected']}")
            else:

                lines.append(f"- input: ({c['input']})")
                lines.append(f"  expected_via_op: \"{c['op']} {c['expected']}\"")
        elif "raw" in c:

            lines.append(f"- raw_assert: {c['raw']}")
    return "\n".join(lines)


def refine_plan_from_logs(
    entry_point: str,
    original_prompt: str,
    prev_plan: Plan,
    failure_logs: str,
    test_code: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    max_tokens: int = 900,
    max_ctx_chars: int = 10000,
) -> Plan:

    _require_key()
    client = OpenAI()
    system = _replan_system_for_format(prev_plan.format)

    failure_logs = _clip(failure_logs, max_ctx_chars // 2)
    test_code = _clip(test_code, max_ctx_chars // 2)

    failing_cases = _extract_failing_asserts(failure_logs, max_cases=6)
    failing_msg = _format_failing_examples_msg(entry_point, failing_cases)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Entry point: {entry_point}\n"
                "HumanEval function signature and docstring (contract):\n"
                f"```\n{original_prompt}\n```"
            ),
        },
    ]

    if failing_msg:
        messages.append({"role": "user", "content": failing_msg})

    messages.extend([
        {"role": "user", "content": "Previous plan (same format):\n" + prev_plan.content},
        {"role": "user", "content": "Official tests (reference):\n" + f"```\n{test_code}\n```"},
        {"role": "user", "content": "Failing logs (full traceback):\n" + f"```\n{failure_logs}\n```"},
        {"role": "user", "content": "Output the corrected plan in the SAME format ONLY."},
    ])

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = (resp.choices[0].message.content or "").strip()
    content = _strip_md_fences(content)
    content = _extract_plan_block(prev_plan.format, content)
    return Plan(prev_plan.format, content)
