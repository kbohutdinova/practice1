import os
import subprocess


TEST_DIR = "tests_pr4"


def run_valid_test(path, expected_path):
    ll_path = "/tmp/practice3_test.ll"

    compile_result = subprocess.run(
        [
            "python3",
            "compiler.py",
            path,
            ll_path,
        ],
        capture_output=True,
        text=True,
    )

    if compile_result.returncode != 0:
        return False, compile_result.stderr.strip()

    run_result = subprocess.run(
        ["lli", ll_path],
        capture_output=True,
        text=True,
    )

    actual = run_result.stdout.strip()

    with open(expected_path, "r") as f:
        expected = f.read().strip()

    return actual == expected, actual


def run_invalid_test(path, expected_path):
    ll_path = "/tmp/practice3_test.ll"

    result = subprocess.run(
        [
            "python3",
            "compiler.py",
            path,
            ll_path,
        ],
        capture_output=True,
        text=True,
    )

    actual = result.stderr.strip()

    with open(expected_path, "r") as f:
        expected = f.read().strip()

    return (
        result.returncode != 0
        and actual == expected
    ), actual


def main():
    passed = 0
    total = 0

    for name in sorted(os.listdir(TEST_DIR)):
        if not name.endswith(".txt"):
            continue

        total += 1

        path = os.path.join(
            TEST_DIR,
            name,
        )

        expected_path = path.replace(
            ".txt",
            ".expected",
        )

        if name.startswith("valid"):
            ok, actual = run_valid_test(
                path,
                expected_path,
            )
        else:
            ok, actual = run_invalid_test(
                path,
                expected_path,
            )

        if ok:
            print(f"{name}: PASS")
            passed += 1
        else:
            print(f"{name}: FAIL")
            print(f"  actual: {actual}")

    print()
    print(f"{passed}/{total} tests passed")


if __name__ == "__main__":
    main()
