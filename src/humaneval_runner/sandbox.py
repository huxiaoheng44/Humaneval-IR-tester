# src/humaneval_runner/sandbox.py
from __future__ import annotations
import subprocess, tempfile, os, sys, shutil
from typing import Tuple, Optional

def run_candidate_with_test(
    candidate_code: str,
    test_code: str,
    entry_point: str | None = None,
    timeout_s: int = 8,
    save_artifact_path: Optional[str] = None,  
) -> Tuple[bool, str]:

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "candidate.py")
        with open(path, "w", encoding="utf-8") as f:

            f.write(candidate_code.rstrip() + "\n\n")

            f.write("if __name__ == '__main__':\n")
            f.write("    import sys, traceback, inspect\n")
            if entry_point:
                f.write(f"    # entry point: {entry_point}\n")
            f.write('    print("[HE] BEGIN_TESTS")\n')
            f.write("    try:\n")

            for line in test_code.splitlines():
                f.write(f"        {line}\n")


            f.write("        _ran_any = False\n")
            f.write("        for _n, _obj in list(globals().items()):\n")
            f.write("            if _n.startswith('test_') and callable(_obj):\n")
            f.write("                _ran_any = True\n")
            f.write("                _obj()\n")


            f.write("        if not _ran_any and 'check' in globals() and callable(globals()['check']):\n")
            if entry_point:
                f.write(f"            globals()['check']({entry_point})\n")
            else:

                f.write("            # no explicit entry_point provided; attempt best-effort call\n")
                f.write("            import builtins\n")
                f.write("            _cands = [v for k, v in globals().items() if callable(v) and k not in dir(builtins)]\n")
                f.write("            if _cands:\n")
                f.write("                try:\n")
                f.write("                    globals()['check'](_cands[0])\n")
                f.write("                except TypeError:\n")
                f.write("                    pass\n")

            f.write("    except Exception:\n")
            f.write("        traceback.print_exc()\n")
            f.write('        print("[HE] END_TESTS (FAILED)")\n')
            f.write("        sys.exit(1)\n")
            f.write("    else:\n")
            f.write('        print("[HE] END_TESTS (PASSED)")\n')
            f.write("        sys.exit(0)\n")


        if save_artifact_path:
            os.makedirs(os.path.dirname(save_artifact_path), exist_ok=True)
            shutil.copy2(path, save_artifact_path)

        try:
            proc = subprocess.run(
                [sys.executable, "-I", path],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return False, f"TIMEOUT after {timeout_s}s"

        logs = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, logs
