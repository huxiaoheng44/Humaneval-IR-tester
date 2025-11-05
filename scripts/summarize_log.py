#!/usr/bin/env python3
# summarize_log.py
from __future__ import annotations
import argparse, json, os, re, sys
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional

def read_jsonl(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception as e:
                print(f"[WARN] skip line {i}: cannot parse JSON ({e})", file=sys.stderr)
    return items

def last_match(pattern: str, text: str, flags: int = 0) -> Optional[str]:
    matches = list(re.finditer(pattern, text, flags))
    return matches[-1].group(0) if matches else None

def classify_from_logs(logs: str) -> Tuple[str, str]:
    """Heuristic fallback when error_type/error_message not provided."""
    if not logs:
        return ("unknown", "")
    upper = logs.upper()
    if "TIMEOUT" in upper:
        return ("timeout", "Execution timed out")

    # common python errors
    for et in [
        "SyntaxError","AssertionError","ModuleNotFoundError","NameError","TypeError",
        "ValueError","ZeroDivisionError","IndexError","KeyError","AttributeError","ImportError"
    ]:
        if et in logs:
            line = last_match(rf"{et}:.*", logs)
            return (et.lower(), line.strip() if line else et)

    # generic traceback tail like "...Error: message"
    if "Traceback (most recent call last):" in logs:
        tail = last_match(r"^[A-Za-z_]\w*Error:.*$", logs, flags=re.M)
        if tail:
            return (tail.split(":",1)[0].strip().lower(), tail.strip())

    # bare assertion
    if last_match(r"^AssertionError$", logs, flags=re.M):
        return ("assertionerror", "AssertionError")

    # fallback
    last = logs.strip().splitlines()[-1] if logs.strip() else ""
    return ("unknown", last[:300])

def extract_error(r: Dict[str, Any]) -> Tuple[str, str]:
    """Prefer recorded error_type/message; else infer from logs."""
    if r.get("passed", False):
        return ("", "")
    et = r.get("error_type")
    em = r.get("error_message")
    if et:
        return (str(et), str(em or ""))
    logs = r.get("logs", "")
    return classify_from_logs(logs)

def markdown_table(rows: List[List[str]], headers: List[str]) -> str:
    # simple Markdown table
    def esc(x: str) -> str:
        return x.replace("\n", " ").replace("|", r"\|").strip()
    widths = [max(len(h), *(len(esc(r[i])) for r in rows)) for i, h in enumerate(headers)]
    def fmt_row(cells: List[str]) -> str:
        return "| " + " | ".join(esc(c).ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    lines = [fmt_row(headers), sep]
    lines += [fmt_row(r) for r in rows]
    return "\n".join(lines)

def plain_table(rows: List[List[str]], headers: List[str]) -> str:
    # fixed-width plain text table
    widths = [max(len(h), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    def fmt_row(cells: List[str]) -> str:
        return "  ".join(str(cells[i]).ljust(widths[i]) for i in range(len(headers)))
    sep = "  ".join("-" * w for w in widths)
    lines = [fmt_row(headers), sep]
    lines += [fmt_row(r) for r in rows]
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser("Summarize HumanEval JSONL logs")
    ap.add_argument("logfile", help="Path to JSONL log (one JSON per line)")
    ap.add_argument("--format", choices=["md","plain"], default="md", help="Table output format")
    ap.add_argument("--show-correct", action="store_true", help="Also list passed tasks (default only failed)")
    ap.add_argument("--max-msg-len", type=int, default=160, help="Trim long error_message to this length")
    args = ap.parse_args()

    if not os.path.exists(args.logfile):
        print(f"[ERROR] file not found: {args.logfile}", file=sys.stderr)
        sys.exit(2)

    recs = read_jsonl(args.logfile)
    if not recs:
        print("[WARN] no records found.")
        sys.exit(0)

    total = len(recs)
    passed = sum(1 for r in recs if r.get("passed", False))
    failed = total - passed
    accuracy = passed / total if total else 0.0

    # build failed rows
    failed_rows: List[List[str]] = []
    err_counter: Counter = Counter()
    for r in recs:
        task_id = str(r.get("task_id","?"))
        if r.get("passed", False):
            continue
        etype, emsg = extract_error(r)
        err_counter[etype or "unknown"] += 1
        # shorten message
        if emsg and len(emsg) > args.max_msg_len:
            emsg = emsg[:args.max_msg_len] + " …"
        plan_format = str(r.get("plan_format",""))
        failed_rows.append([task_id, plan_format, etype or "unknown", emsg or ""])

    # optionally show correct rows
    passed_rows: List[List[str]] = []
    if args.show_correct:
        for r in recs:
            if r.get("passed", False):
                passed_rows.append([str(r.get("task_id","?")), str(r.get("plan_format",""))])

    # print summary
    print("=== SUMMARY ===")
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Accuracy(pass@1): {accuracy:.3f}")

    if failed_rows:
        print("\n=== FAILED TASKS ===")
        headers = ["task_id", "plan_format", "error_type", "error_message"]
        table = markdown_table(failed_rows, headers) if args.format == "md" else plain_table(failed_rows, headers)
        print(table)
        print("\n--- Failure breakdown ---")
        for et, cnt in err_counter.most_common():
            print(f"{et}: {cnt}")
    else:
        print("\nNo failed tasks 🎉")

    if args.show_correct and passed_rows:
        print("\n=== PASSED TASKS ===")
        headers_ok = ["task_id", "plan_format"]
        table_ok = markdown_table(passed_rows, headers_ok) if args.format == "md" else plain_table(passed_rows, headers_ok)
        print(table_ok)

if __name__ == "__main__":
    main()
