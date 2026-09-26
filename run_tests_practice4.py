import os
import subprocess
import sys
import tempfile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMPILER = os.path.join(BASE_DIR, "compiler.py")

OK_DIR = os.path.join(BASE_DIR, "tests", "ok")
ERR_DIR = os.path.join(BASE_DIR, "tests", "err")


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def run_ok_test(source_path, expected_path):
    with tempfile.NamedTemporaryFile(
        suffix=".ll",
        delete=False,
    ) as tmp:
        output_path = tmp.name

    try:
        compile_result = subprocess.run(
            [
                sys.executable,
                COMPILER,
                source_path,
                output_path,
            ],
            capture_output=True,
            text=True,
        )

        if compile_result.returncode != 0:
            return (
                False,
                "compiler failed:\n"
                + compile_result.stderr.strip(),
            )

        run_result = subprocess.run(
            ["lli", output_path],
            capture_output=True,
            text=True,
        )

        if run_result.returncode != 0:
            return (
                False,
                "lli failed:\n"
                + run_result.stderr.strip(),
            )

        actual = run_result.stdout.strip()
        expected = read_text(expected_path)

        if actual != expected:
            return (
                False,
                f"expected:\n{expected}\n"
                f"actual:\n{actual}",
            )

        return True, ""

    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def run_err_test(source_path, expected_path):
    with tempfile.NamedTemporaryFile(
        suffix=".ll",
        delete=False,
    ) as tmp:
        output_path = tmp.name

    os.remove(output_path)

    result = subprocess.run(
        [
            sys.executable,
            COMPILER,
            source_path,
            output_path,
        ],
        capture_output=True,
        text=True,
    )

    expected = read_text(expected_path)
    actual = result.stderr.strip()

    if result.returncode == 0:
        if os.path.exists(output_path):
            os.remove(output_path)

        return (
            False,
            "compiler succeeded, but an error was expected",
        )

    if os.path.exists(output_path):
        os.remove(output_path)

        return (
            False,
            "compiler left an output file after an error",
        )

    if actual != expected:
        return (
            False,
            f"expected:\n{expected}\n"
            f"actual:\n{actual}",
        )

    return True, ""


def collect_tests(directory):
    tests = []

    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".txt"):
            continue

        base = filename[:-4]

        source_path = os.path.join(
            directory,
            filename,
        )

        expected_path = os.path.join(
            directory,
            base + ".expected",
        )

        if not os.path.exists(expected_path):
            print(
                f"{base}: FAIL "
                "(missing .expected)"
            )
            continue

        tests.append(
            (
                base,
                source_path,
                expected_path,
            )
        )

    return tests


def main():
    total = 0
    passed = 0

    print("Practice 4 OK tests")

    for (
        name,
        source_path,
        expected_path,
    ) in collect_tests(OK_DIR):
        total += 1

        ok, message = run_ok_test(
            source_path,
            expected_path,
        )

        if ok:
            passed += 1
            print(f"{name}: PASS")
        else:
            print(f"{name}: FAIL")
            print(message)

    print()
    print("Practice 4 ERR tests")

    for (
        name,
        source_path,
        expected_path,
    ) in collect_tests(ERR_DIR):
        total += 1

        ok, message = run_err_test(
            source_path,
            expected_path,
        )

        if ok:
            passed += 1
            print(f"{name}: PASS")
        else:
            print(f"{name}: FAIL")
            print(message)

    print()
    print(f"{passed}/{total} tests passed")

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
