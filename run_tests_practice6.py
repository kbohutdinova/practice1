import glob
import os
import subprocess
import sys

COMPILER = "compiler.py"
OUTPUT = "/tmp/practice6_test.ll"

passed = 0
failed = 0


def read_expected(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def run_ok(path):
    global passed, failed

    expected_path = path.replace(".txt", ".expected")
    expected = read_expected(expected_path)

    compile_result = subprocess.run(
        [
            sys.executable,
            COMPILER,
            path,
            OUTPUT,
        ],
        capture_output=True,
        text=True,
    )

    if compile_result.returncode != 0:
        print(f"FAIL {path}")
        print("Compilation failed:")
        print(compile_result.stderr.strip())
        failed += 1
        return

    lli_result = subprocess.run(
        ["lli", OUTPUT],
        capture_output=True,
        text=True,
    )

    actual = lli_result.stdout.strip()

    if lli_result.returncode != 0:
        print(f"FAIL {path}")
        print("lli failed:")
        print(lli_result.stderr.strip())
        failed += 1
        return

    if actual != expected:
        print(f"FAIL {path}")
        print(f"Expected: {expected!r}")
        print(f"Actual:   {actual!r}")
        failed += 1
        return

    print(f"PASS {path}")
    passed += 1


def run_err(path):
    global passed, failed

    expected_path = path.replace(".txt", ".expected")
    expected = read_expected(expected_path)

    result = subprocess.run(
        [
            sys.executable,
            COMPILER,
            path,
            OUTPUT,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"FAIL {path}")
        print("Expected compilation error, but compilation succeeded.")
        failed += 1
        return

    actual = result.stderr.strip()

    if expected not in actual:
        print(f"FAIL {path}")
        print(f"Expected stderr to contain: {expected!r}")
        print(f"Actual stderr: {actual!r}")
        failed += 1
        return

    print(f"PASS {path}")
    passed += 1


for path in sorted(glob.glob("tests/ok/p6_*.txt")):
    run_ok(path)

for path in sorted(glob.glob("tests/err/p6_*.txt")):
    run_err(path)

if os.path.exists(OUTPUT):
    os.remove(OUTPUT)

total = passed + failed

print()
print(f"Passed {passed}/{total}")

if failed:
    sys.exit(1)
