# Humaneval-IR Tester

## Overview
Humaneval-IR Tester is a lightweight harness for studying "plan → code → test" pipelines on HumanEval-style tasks. The runner prompts an OpenAI chat model to draft a structured plan, converts that plan into Python code, and executes the official unit tests inside an isolated sandbox. Optional re-planning and code-repair loops make it easy to measure how different plan formats or model choices affect pass rates.

## Features
- **Multiple plan formats** – natural language, YAML, DSL, and Mermaid flowcharts are supported out of the box through tailored few-shot prompts.【F:src/humaneval_runner/plan_prompts.py†L18-L205】
- **Automated plan generation and refinement** – utilities call OpenAI chat completions to draft plans and, when needed, regenerate them using failure logs plus test context.【F:src/humaneval_runner/planner_per_format.py†L14-L253】
- **Plan-grounded code synthesis** – code is generated (and optionally repaired) strictly from the selected plan format, enforcing contract adherence to the HumanEval prompt.【F:src/humaneval_runner/codegen_from_plan.py†L13-L216】
- **Deterministic sandbox execution** – each candidate solution is run with the authoritative HumanEval tests inside an isolated `python -I` process that captures logs and enforces a timeout.【F:src/humaneval_runner/sandbox.py†L6-L76】
- **CLI tooling for experiments and reporting** – `scripts/run_eval.py` orchestrates end-to-end evaluations and emits JSONL logs, while `scripts/summarize_log.py` aggregates accuracy and failure categories.【F:scripts/run_eval.py†L17-L123】【F:scripts/summarize_log.py†L8-L158】

## Repository layout
```
.
├── data/                # Bundled HumanEval JSONL benchmark
├── scripts/             # Command-line entry points for running & summarizing experiments
└── src/humaneval_runner/ # Core planning, codegen, and sandbox utilities
```

Key modules:
- `dataset.py` – loads HumanEval JSONL files and normalizes missing entry points.【F:src/humaneval_runner/dataset.py†L5-L25】
- `planner_per_format.py` – prompt builders, plan generation, and re-planning routines.【F:src/humaneval_runner/planner_per_format.py†L14-L253】
- `codegen_from_plan.py` – translates plans into code and repairs failing implementations.【F:src/humaneval_runner/codegen_from_plan.py†L13-L216】
- `evaluator_plan_then_code.py` – high-level loop that chains planning, coding, testing, and optional repair per task.【F:src/humaneval_runner/evaluator_plan_then_code.py†L28-L127】
- `sandbox.py` – executes candidate code against tests in a temporary working directory.【F:src/humaneval_runner/sandbox.py†L6-L76】

## Requirements
- Python 3.10 or later
- An OpenAI API key with access to the specified models (default: `gpt-4o-mini`)
- Python packages: `openai` (latest SDK) and the standard library only

Install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade openai
```

Set your API key before running the tools:
```bash
export OPENAI_API_KEY="sk-..."
```
All model-facing helpers raise a runtime error when the key is missing, so the environment variable must be present.【F:src/humaneval_runner/planner_per_format.py†L9-L40】【F:src/humaneval_runner/codegen_from_plan.py†L8-L126】

## Running an evaluation
Use `scripts/run_eval.py` to evaluate one or more HumanEval problems end-to-end.

```bash
python scripts/run_eval.py \
  --data data/HumanEval.jsonl \
  --plan-format nl \
  --model-plan gpt-4o-mini \
  --model-code gpt-4o-mini \
  --replan-on-fail \
  --replan-rounds 2 \
  --repair-rounds 1
```

Important flags:
- `--plan-format`: choose among `nl`, `yaml`, `dsl`, or `mermaid` plan representations.【F:scripts/run_eval.py†L22-L77】
- `--replan-on-fail` / `--replan-rounds`: enable iterative plan refinement when the first attempt fails.【F:scripts/run_eval.py†L30-L77】【F:src/humaneval_runner/evaluator_plan_then_code.py†L59-L85】
- `--repair-rounds`: attempt plan-guided code repair after re-planning is exhausted.【F:scripts/run_eval.py†L33-L77】【F:src/humaneval_runner/evaluator_plan_then_code.py†L87-L110】
- `--limit`: restrict the number of tasks loaded from the dataset file.【F:scripts/run_eval.py†L23-L50】

The script writes one JSON object per task to `runs/<plan_format>__plan-<model>__code-<model>.jsonl` by default.【F:scripts/run_eval.py†L17-L105】 Each record captures the task metadata, rendered plan, generated code, pass/fail status, and any execution logs.

## Understanding the JSONL output
Each evaluation row contains:
- `task_id`, `plan_format`, `plan`, `code`, and `passed` fields.
- `replanned`/`replan_rounds_used` and `repaired`/`repair_rounds_used` counters for tracing intervention depth.【F:scripts/run_eval.py†L83-L103】【F:src/humaneval_runner/evaluator_plan_then_code.py†L111-L127】
- On failure, a `logs` field stores the captured traceback from the sandbox.【F:scripts/run_eval.py†L99-L105】【F:src/humaneval_runner/sandbox.py†L52-L76】

## Summarizing results
After a run, produce a concise report with:
```bash
python scripts/summarize_log.py runs/nl__plan-gpt-4o-mini__code-gpt-4o-mini.jsonl --format md
```
The summarizer prints aggregate accuracy, per-task failure rows, and a breakdown of inferred error types. Use `--show-correct` to also list tasks that passed.【F:scripts/summarize_log.py†L89-L158】

## Dataset
The repository ships the canonical `data/HumanEval.jsonl`, but any HumanEval-compatible JSONL file can be supplied. Each line should contain the `task_id`, Python function `prompt` (signature + docstring), `entry_point`, and `test` payload used by the runner.【F:src/humaneval_runner/dataset.py†L5-L25】 Use `--limit` to sample a subset during quick experiments.【F:scripts/run_eval.py†L23-L50】

## Tips & customization
- Swap `--model-plan` and `--model-code` to benchmark alternative OpenAI chat models without editing code.【F:scripts/run_eval.py†L26-L77】
- Modify or extend `plan_prompts.py` to experiment with new planning styles or few-shot exemplars.【F:src/humaneval_runner/plan_prompts.py†L18-L205】
- The sandbox helper can persist generated candidates for debugging by supplying `save_artifact_path` when calling `run_candidate_with_test`.【F:src/humaneval_runner/sandbox.py†L6-L76】
- Integrate additional analytics by parsing the JSONL logs or building on `summarize_log.py`'s table utilities.【F:scripts/summarize_log.py†L8-L158】

## Troubleshooting
- **`OPENAI_API_KEY not set`** – ensure the environment variable is exported before running; every OpenAI call checks for it.【F:src/humaneval_runner/planner_per_format.py†L9-L40】【F:src/humaneval_runner/codegen_from_plan.py†L8-L126】
- **Timeouts** – increase `--timeout` in `run_eval.py` if complex tasks need more than 8 seconds of execution time.【F:scripts/run_eval.py†L21-L77】【F:src/humaneval_runner/sandbox.py†L6-L76】
- **Model output with Markdown fences** – the pipeline strips backticks and recovers the plan/code automatically, but keeping outputs raw minimizes cleanup work.【F:src/humaneval_runner/planner_per_format.py†L69-L98】【F:src/humaneval_runner/codegen_from_plan.py†L62-L126】

Enjoy exploring plan-informed code generation on HumanEval!
