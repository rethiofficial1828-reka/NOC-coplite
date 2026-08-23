#!/usr/bin/env python3
"""
NOC Copilot — Live Verification Runner
Run: PYTHONPATH=. ./venv/bin/python3 live_verification_runner.py
Results written to: data/LIVE_VERIFICATION_RESULTS.txt
"""
import io
import json
import os
import subprocess
import sys
import time
import unittest
import warnings

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

OUT_FILE = os.path.join(ROOT, 'data', 'LIVE_VERIFICATION_RESULTS.txt')
os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)

DIVIDER = '=' * 72


def run_suite(name, stream):
    stream.write(f'\n{DIVIDER}\n')
    stream.write(f'SUITE: {name}\n')
    stream.write(f'{DIVIDER}\n')
    buf = io.StringIO()
    t0 = time.perf_counter()
    try:
        # suppress ResourceWarning noise in output — we audit separately
        warnings.simplefilter('ignore', ResourceWarning)
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(name)
        runner = unittest.TextTestRunner(stream=buf, verbosity=2, warnings='ignore')
        result = runner.run(suite)
        elapsed = time.perf_counter() - t0
        n = result.testsRun
        f = len(result.failures)
        e = len(result.errors)
        s = len(result.skipped) if hasattr(result, 'skipped') else 0
        p = n - f - e
        status = 'PASS' if result.wasSuccessful() else 'FAIL'
        stream.write(buf.getvalue())
        stream.write(f'\nRESULT: ran={n} pass={p} fail={f} err={e} skip={s} '
                     f'status={status} time={elapsed:.3f}s\n')
        if result.failures:
            stream.write('\n--- FAILURES ---\n')
            for t, tb in result.failures:
                stream.write(f'FAIL: {t}\n{tb}\n')
        if result.errors:
            stream.write('\n--- ERRORS (first 3) ---\n')
            for t, tb in result.errors[:3]:
                stream.write(f'ERROR: {t}\n{tb}\n')
            if len(result.errors) > 3:
                stream.write(f'... +{len(result.errors)-3} more\n')
        return {'suite': name, 'ran': n, 'pass': p, 'fail': f, 'err': e,
                'skip': s, 'status': status, 'time': round(elapsed, 3)}
    except Exception as ex:
        elapsed = time.perf_counter() - t0
        stream.write(f'LOAD/IMPORT ERROR: {ex}\n')
        import traceback
        traceback.print_exc(file=stream)
        return {'suite': name, 'ran': 0, 'pass': 0, 'fail': 0, 'err': 1,
                'skip': 0, 'status': f'ERROR: {ex}', 'time': round(elapsed, 3)}


def run_script(label, cmd, stream, timeout=60):
    stream.write(f'\n{DIVIDER}\n')
    stream.write(f'SCRIPT: {label}\n')
    stream.write(f'CMD: {cmd}\n')
    stream.write(f'{DIVIDER}\n')
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=ROOT
        )
        elapsed = time.perf_counter() - t0
        stream.write(proc.stdout[-8000:] if len(proc.stdout) > 8000 else proc.stdout)
        if proc.stderr:
            stream.write('\n--- STDERR ---\n')
            stream.write(proc.stderr[-3000:] if len(proc.stderr) > 3000 else proc.stderr)
        stream.write(f'\nRETURN CODE: {proc.returncode}  TIME: {elapsed:.3f}s\n')
        return proc.returncode, elapsed
    except subprocess.TimeoutExpired:
        stream.write(f'TIMEOUT after {timeout}s\n')
        return -1, timeout
    except Exception as ex:
        stream.write(f'ERROR: {ex}\n')
        return -2, 0.0


with open(OUT_FILE, 'w', encoding='utf-8') as out:
    out.write(DIVIDER + '\n')
    out.write('NOC COPILOT — LIVE VERIFICATION RUN\n')
    out.write(f'Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n')
    out.write(f'Python: {sys.version}\n')
    out.write(DIVIDER + '\n')

    results = []

    # ── 1. Matrix ─────────────────────────────────────────────────────────────
    results.append(run_suite('tests.test_matrix_10000', out))
    out.flush()

    # ── 2. Adaptive Failover ──────────────────────────────────────────────────
    results.append(run_suite('tests.test_adaptive_failover', out))
    out.flush()

    # ── 3. Failover Agent ─────────────────────────────────────────────────────
    results.append(run_suite('tests.test_failover_agent', out))
    out.flush()

    # ── 4. Path Decision ──────────────────────────────────────────────────────
    results.append(run_suite('tests.test_path_decision', out))
    out.flush()

    # ── 5. Federated Intelligence ─────────────────────────────────────────────
    results.append(run_suite('tests.test_federated_intelligence', out))
    out.flush()

    # ── 6. UI Streamlit ───────────────────────────────────────────────────────
    results.append(run_suite('tests.test_ui_streamlit', out))
    out.flush()

    # ── 7. Runtime check-only ─────────────────────────────────────────────────
    venv_py = os.path.join(ROOT, 'venv', 'bin', 'python3')
    if not os.path.exists(venv_py):
        venv_py = sys.executable
    run_script(
        'run.py --check-only',
        f'PYTHONPATH={ROOT} {venv_py} {ROOT}/run.py --check-only',
        out,
        timeout=30
    )
    out.flush()

    # ── 8. Realistic E2E Demo ─────────────────────────────────────────────────
    run_script(
        'run_realistic_simulation_demo.py',
        f'PYTHONPATH={ROOT} {venv_py} {ROOT}/tests/run_realistic_simulation_demo.py',
        out,
        timeout=120
    )
    out.flush()

    # ── 9. Full 10000 matrix runner ───────────────────────────────────────────
    run_script(
        'run_10000_validation_matrix.py',
        f'PYTHONPATH={ROOT} {venv_py} {ROOT}/tests/run_10000_validation_matrix.py',
        out,
        timeout=300
    )
    out.flush()

    # ── Aggregate Summary ─────────────────────────────────────────────────────
    out.write(f'\n{DIVIDER}\n')
    out.write('AGGREGATE SUMMARY\n')
    out.write(f'{DIVIDER}\n')
    total_ran = sum(r['ran'] for r in results)
    total_pass = sum(r['pass'] for r in results)
    total_fail = sum(r['fail'] for r in results)
    total_err = sum(r['err'] for r in results)
    total_time = sum(r['time'] for r in results)
    out.write(f'{"Suite":<45} {"Ran":>6} {"Pass":>6} {"Fail":>5} {"Err":>5} {"Status"}\n')
    out.write('-' * 80 + '\n')
    for r in results:
        out.write(f'{r["suite"]:<45} {r["ran"]:>6} {r["pass"]:>6} {r["fail"]:>5} {r["err"]:>5}  {r["status"]}\n')
    out.write('-' * 80 + '\n')
    out.write(f'{"TOTAL":<45} {total_ran:>6} {total_pass:>6} {total_fail:>5} {total_err:>5}\n')
    pct = (total_pass / total_ran * 100) if total_ran > 0 else 0.0
    out.write(f'\nPass rate: {pct:.2f}%  ({total_pass}/{total_ran})\n')
    out.write(f'Total time (suites only): {total_time:.2f}s\n')
    out.write(DIVIDER + '\n')

print(f'[live_verification_runner] Complete. Results -> {OUT_FILE}')
