#!/usr/bin/env python3
from __future__ import annotations
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import argparse, json
from pathlib import Path
from typing import List, Dict

from humaneval_runner.dataset import load_humaneval_jsonl
from humaneval_runner.plans import PlanFormat
from humaneval_runner.evaluator_plan_then_code import eval_plan_then_code

def build_default_out(plan_format: str, model_plan: str, model_code: str) -> str:
    safe = lambda s: s.replace("/", "_")
    return f"runs/{plan_format}__plan-{safe(model_plan)}__code-{safe(model_code)}.jsonl"

def main():
    ap = argparse.ArgumentParser("HumanEval Plan→Code→Test (with replan & repair)")
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--plan-format", choices=["nl", "yaml", "dsl", "mermaid"], default="nl")
    ap.add_argument("--model-plan", default="gpt-4o-mini")
    ap.add_argument("--model-code", default="gpt-4o-mini")
    ap.add_argument("--timeout", type=int, default=8)

    ap.add_argument("--replan-on-fail", action="store_true", help="On initial failure, try to re-plan before repairing")
    ap.add_argument("--replan-rounds", type=int, default=3, help="How many re-plan rounds to try on failure")

    ap.add_argument("--repair-rounds", type=int, default=0, help="Attempt this many repair rounds on failure")

    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.data):
        print(f"[ERROR] Data file not found: {args.data}")
        return 2

    out_path = args.out or build_default_out(args.plan_format, args.model_plan, args.model_code)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Logging to: {out_path}")

    problems: List[Dict] = load_humaneval_jsonl(args.data, limit=args.limit)
    if not problems:
        print("[WARN] Loaded 0 tasks. Check your JSONL path/content.")
        return 0

    print(f"[INFO] Loaded {len(problems)} tasks from {args.data}")
    print(f"[INFO] Plan format = {args.plan_format}, plan-model = {args.model_plan}, code-model = {args.model_code}")
    if args.replan_on_fail:
        print(f"[INFO] Re-PLAN on fail: rounds={args.replan_rounds}")
    if args.repair_rounds:
        print(f"[INFO] Code repair rounds = {args.repair_rounds}")

    pf = PlanFormat(args.plan_format)
    passed_cnt = 0
    results_all = []

    with open(out_path, "w", encoding="utf-8") as fout:
        for i, problem in enumerate(problems, start=1):
            task_id = problem.get("task_id", "?")
            print(f"[RUN] Task {i}/{len(problems)}: {task_id}")

            rs = eval_plan_then_code(
                [problem],
                fmt=pf,
                model_plan=args.model_plan,
                model_code=args.model_code,
                timeout_s=args.timeout,
                replan_on_fail=args.replan_on_fail,
                replan_rounds=args.replan_rounds,
                repair_rounds=args.repair_rounds,
            )
            r = rs[0]
            results_all.append(r)
            if r.passed:
                passed_cnt += 1

            tag = []
            if r.replanned: tag.append("replanned")
            if r.repaired:  tag.append("repaired")
            tag_str = f" ({', '.join(tag)})" if tag else ""
            print(f"      → {'PASS' if r.passed else 'FAIL'}{tag_str}")

            record = {
                "task_id": task_id,
                "plan_format": pf.value,
                "plan": r.plan_text,             
                "code": r.code_text,             
                "passed": r.passed,
                "replanned": r.replanned,
                "replan_rounds_used": r.replan_rounds_used,
                "repaired": r.repaired,
                "repair_rounds_used": r.repair_rounds_used,
            }
            if not r.passed:
                record["logs"] = r.logs  

            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            fout.flush()

            if args.verbose:
                print("------ PLAN ------")
                print(r.plan_text)
                print("------------------")
                if not r.passed:
                    print("------ LOGS ------")
                    print(r.logs)
                    print("------------------")

    total = len(results_all)
    acc = passed_cnt / total if total else 0.0
    print("\n=== SUMMARY ===")
    print(f"Total: {total}, Passed: {passed_cnt}, Accuracy(pass@1)={acc:.3f}")
    print(f"[INFO] Log saved at: {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
