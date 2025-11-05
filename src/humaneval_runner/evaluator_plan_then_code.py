# src/humaneval_runner/evaluator_plan_then_code.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional

from .plans import PlanFormat
from .planner_per_format import make_plan, refine_plan_from_logs
from .codegen_from_plan import generate_code_from_plan, repair_code_with_feedback  # 如果没有修复函数，可删去本行与后续 repair 逻辑
from .sandbox import run_candidate_with_test

@dataclass
class EvalResult:
    task_id: str
    plan_text: str              
    code_text: str              
    passed: bool
    logs: str                  

    replanned: bool = False
    replan_rounds_used: int = 0

    repaired: bool = False
    repair_rounds_used: int = 0

    first_code: Optional[str] = None
    first_logs: Optional[str] = None

def eval_plan_then_code(
    problems: List[Dict],
    fmt: PlanFormat,
    model_plan: str = "gpt-4o-mini",
    model_code: str = "gpt-4o-mini",
    timeout_s: int = 8,

    replan_on_fail: bool = True,
    replan_rounds: int = 1,
    repair_rounds: int = 0,
) -> List[EvalResult]:
    results: List[EvalResult] = []

    for p in problems:
        task_id = p.get("task_id", "unknown")
        prompt = p["prompt"]
        entry_point = p["entry_point"]
        test = p["test"]

        plan = make_plan(entry_point, prompt, fmt, model=model_plan)
        code0 = generate_code_from_plan(entry_point, prompt, plan, model=model_code)
        passed, logs = run_candidate_with_test(code0, test, entry_point=entry_point, timeout_s=timeout_s)

        replanned = False
        replan_used = 0
        repaired = False
        repair_used = 0
        code_final = code0
        first_logs = None


        if not passed and replan_on_fail and replan_rounds > 0:
            first_logs = logs
            prev_plan = plan
            for r in range(replan_rounds):
                new_plan = refine_plan_from_logs(
                    entry_point=entry_point,
                    original_prompt=prompt,
                    prev_plan=prev_plan,
                    failure_logs=logs,
                    test_code=test,
                    model=model_plan,
                )
                code_try = generate_code_from_plan(entry_point, prompt, new_plan, model=model_code)
                passed_try, logs_try = run_candidate_with_test(
                    code_try, test, entry_point=entry_point, timeout_s=timeout_s
                )
                replan_used = r + 1
                replanned = True

                prev_plan = new_plan
                plan = new_plan
                code_final = code_try
                passed = passed_try
                logs = logs_try
                if passed_try:
                    break


        if not passed and repair_rounds > 0:
            prev_code, prev_logs = code_final, logs
            for r in range(repair_rounds):
                code_try = repair_code_with_feedback(
                    entry_point=entry_point,
                    original_prompt=prompt,
                    plan=plan,              
                    bad_code=prev_code,
                    failure_logs=prev_logs, 
                    test_code=test,        
                    model=model_code,
                )
                passed_try, logs_try = run_candidate_with_test(
                    code_try, test, entry_point=entry_point, timeout_s=timeout_s
                )
                repair_used = r + 1

                prev_code, prev_logs = code_try, logs_try
                code_final, logs = code_try, logs_try
                if passed_try:
                    repaired = True
                    passed = True
                    break

        results.append(
            EvalResult(
                task_id=task_id,
                plan_text=plan.content,   
                code_text=code_final,
                passed=passed,
                logs=logs or "",
                replanned=replanned,
                replan_rounds_used=replan_used,
                repaired=repaired,
                repair_rounds_used=repair_used,
                first_code=code0,
                first_logs=first_logs,
            )
        )

    return results
