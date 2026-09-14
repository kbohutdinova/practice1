import subprocess
import os


def run_valid_test(name):
    input_file = f"tests/{name}.txt"
    expected_file = f"tests/{name}.expected"
    output_file = f"tests/{name}.ll"

    result = subprocess.run(
        [
            "python3",
            "compiler.py",
            input_file,
            output_file,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"{name}: FAIL")
        print(result.stderr.strip())
        return False

    run_result = subprocess.run(
        ["lli", output_file],
        capture_output=True,
        text=True,
    )

    with open(expected_file, "r") as f:
        expected = f.read().strip()

    actual = run_result.stdout.strip()

    if actual == expected:
        print(f"{name}: PASS")
        return True

    print(f"{name}: FAIL")
    print(f"expected: {expected}")
    print(f"actual:   {actual}")
    return False


def run_invalid_test(name):
    input_file = f"tests/{name}.txt"
    expected_file = f"tests/{name}.expected"
    output_file = f"tests/{name}.ll"

    result = subprocess.run(
        [
            "python3",
            "compiler.py",
            input_file,
            output_file,
        ],
        capture_output=True,
        text=True,
    )

    with open(expected_file, "r") as f:
        expected = f.read().strip()

    actual = result.stderr.strip()

    if (
        result.returncode != 0
        and actual == expected
        and not os.path.exists(output_file)
    ):
        print(f"{name}: PASS")
        return True

    print(f"{name}: FAIL")
    print(f"expected: {expected}")
    print(f"actual:   {actual}")
    print(f"return code: {result.returncode}")
    return False


def main():
    passed = 0
    total = 0

    for i in range(1, 6):
        total += 1
        if run_valid_test(f"valid{i}"):
            passed += 1

    for i in range(1, 6):
        total += 1
        if run_invalid_test(f"invalid{i}"):
            passed += 1

    print()
    print(f"{passed}/{total} tests passed")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
