import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
COMPILER = ROOT / "src" / "compiler.py"
TESTS = ROOT / "tests"
OUTPUT_LL = ROOT / "output.ll"


def read_expected(path: Path) -> str:
    return path.read_text().strip()


def run_ok_test(test_path: Path) -> tuple[bool, str]:
    expected_path = test_path.with_suffix(".expected")
    expected = read_expected(expected_path)

    compile_result = subprocess.run(
        ["python3", str(COMPILER), str(test_path), str(OUTPUT_LL)],
        capture_output=True,
        text=True,
    )

    if compile_result.returncode != 0:
        actual = (compile_result.stdout + compile_result.stderr).strip()
        return False, f"compiler failed:\n{actual}"

    lli_result = subprocess.run(
        ["lli", str(OUTPUT_LL)],
        capture_output=True,
        text=True,
    )

    actual = (lli_result.stdout + lli_result.stderr).strip()

    if actual == expected:
        return True, ""

    return False, f"expected:\n{expected}\nactual:\n{actual}"


def run_err_test(test_path: Path) -> tuple[bool, str]:
    expected_path = test_path.with_suffix(".expected")
    expected = read_expected(expected_path)

    result = subprocess.run(
        ["python3", str(COMPILER), str(test_path), str(OUTPUT_LL)],
        capture_output=True,
        text=True,
    )

    actual = (result.stdout + result.stderr).strip()

    if actual == expected:
        return True, ""

    return False, f"expected:\n{expected}\nactual:\n{actual}"


def run_group(name: str, folder: Path, runner):
    print(name)

    passed = 0
    total = 0

    for test_path in sorted(folder.glob("*.txt")):
        total += 1
        ok, details = runner(test_path)

        if ok:
            passed += 1
            print(f"{test_path.stem}: PASS")
        else:
            print(f"{test_path.stem}: FAIL")
            print(details)

    print()
    return passed, total


def main():
    ok_passed, ok_total = run_group(
        "Practice 5 OK tests",
        TESTS / "ok",
        run_ok_test,
    )

    err_passed, err_total = run_group(
        "Practice 5 ERR tests",
        TESTS / "err",
        run_err_test,
    )

    passed = ok_passed + err_passed
    total = ok_total + err_total

    print(f"{passed}/{total} tests passed")

    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
