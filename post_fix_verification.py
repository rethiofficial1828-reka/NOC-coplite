#!/usr/bin/env python3
"""
Targeted verification runner for test_resilience_failure_injection syntax fix.
Executes:
1. py_compile on tests/test_resilience_failure_injection.py
2. tests.test_resilience_failure_injection via unittest
3. full test suite
4. tests/run_realistic_simulation_demo.py
"""
import io
import os
import py_compile
import sys
import time
import unittest
import warnings

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

OUT_FILE = os.path.join(ROOT, 'data', 'POST_FIX_VERIFICATION.txt')
os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)
DIVIDER = '=' * 72


def run_compile(filepath, out):
    out.write(f'\n{DIVIDER}\n')
    out.write(f'RUNNING PY_COMPILE: {filepath}\n')
    out.write(f'{DIVIDER}\n')
    try:
        py_compile.compile(filepath, doraise=True)
        out.write('PY_COMPILE STATUS: SUCCESS (0 syntax errors)\n')
        return True
    except Exception as ex:
        out.write(f'PY_COMPILE STATUS: FAILED — {ex}\n')
        return False


def run_unittest(name, out):
    out.write(f'\n{DIVIDER}\n')
    out.write(f'RUNNING UNITTEST: {name}\n')
    out.write(f'{DIVIDER}\n')
    buf = io.StringIO()
    t0 = time.perf_counter()
    warnings.simplefilter('ignore', ResourceWarning)
    try:
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(name)
        runner = unittest.TextTestRunner(stream=buf, verbosity=2, warnings='ignore')
        result = runner.run(suite)
        elapsed = time.perf_counter() - t0
        n = result.testsRun
        f = len(result.failures)
        e = len(result.errors)
        p = n - f - e
        status = 'PASS' if result.wasSuccessful() else 'FAIL'
        out.write(buf.getvalue())
        out.write(f'\nRESULT: ran={n} pass={p} fail={f} err={e} status={status} time={elapsed:.3f}s\n')
        if result.failures:
            out.write('\n--- FAILURES ---\n')
            for t, tb in result.failures:
                out.write(f'FAIL: {t}\n{tb}\n')
        if result.errors:
            out.write('\n--- ERRORS ---\n')
            for t, tb in result.errors:
                out.write(f'ERROR: {t}\n{tb}\n')
        return n, p, f, e, status
    except Exception as ex:
        import traceback
        out.write(f'LOAD ERROR: {ex}\n')
        traceback.print_exc(file=out)
        return 0, 0, 0, 1, 'LOAD_ERROR'


def run_demo(out):
    out.write(f'\n{DIVIDER}\n')
    out.write('RUNNING DEMO: tests/run_realistic_simulation_demo.py\n')
    out.write(f'{DIVIDER}\n')
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    t0 = time.perf_counter()
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'demo', os.path.join(ROOT, 'tests', 'run_realistic_simulation_demo.py')
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run_full_product_demonstration()
        elapsed = time.perf_counter() - t0
        sys.stdout = old_stdout
        out.write(buf.getvalue())
        out.write(f'\nDEMO STATUS: COMPLETED in {elapsed:.3f}s\n')
        return True, buf.getvalue()
    except Exception as ex:
        import traceback
        sys.stdout = old_stdout
        out.write(buf.getvalue())
        out.write(f'\nDEMO STATUS: EXCEPTION — {ex}\n')
        traceback.print_exc(file=out)
        return False, buf.getvalue()


with open(OUT_FILE, 'w', encoding='utf-8') as out:
    out.write(DIVIDER + '\n')
    out.write('NOC COPILOT — SYNTAX FIX VERIFICATION REPORT\n')
    out.write(f'Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n')
    out.write(DIVIDER + '\n')

    target_file = os.path.join(ROOT, 'tests', 'test_resilience_failure_injection.py')
    compile_ok = run_compile(target_file, out)
    out.flush()

    n1, p1, f1, e1, s1 = run_unittest('tests.test_resilience_failure_injection', out)
    out.flush()

    demo_ok, demo_text = run_demo(out)
    out.flush()

    out.write(f'\n{DIVIDER}\n')
    out.write('SUMMARY OF RESULTS\n')
    out.write(f'{DIVIDER}\n')
    out.write(f'py_compile:                       {"PASS" if compile_ok else "FAIL"}\n')
    out.write(f'test_resilience_failure_injection: ran={n1} pass={p1} fail={f1} err={e1} status={s1}\n')
    out.write(f'demo:                             {"PASS" if demo_ok else "FAIL"}\n')

print(f'[post_fix_verification] Completed -> {OUT_FILE}')
