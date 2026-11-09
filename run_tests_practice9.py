import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPILER = ROOT / "compiler.py"
INPUT_DATA = "10\n20\n30\n40\n50\n"


def run_command(args, input_data=None):
    try:
        return subprocess.run(
            args,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=ROOT
        )
    except subprocess.TimeoutExpired:
        return None


def compile_file(source, output, optimize):
    args = ["python3", str(COMPILER)]

    if optimize:
        args.append("--remove-unused")

    args.extend([str(source), str(output)])
    return run_command(args)


def run_program(output):
    return run_command(["lli", str(output)], INPUT_DATA)


def check_opt_test(source, output):
    expected_output = source.with_suffix(".expected").read_text()
    expected_ast = source.with_suffix(".astc").read_text()

    ast_result = run_command([
        "python3",
        str(COMPILER),
        "--remove-unused",
        "--ast-checked",
        str(source)
    ])

    if ast_result is None or ast_result.returncode != 0:
        return False, "AST generation failed"

    if ast_result.stdout != expected_ast:
        return False, "AST does not match .astc"

    for optimize in (False, True):
        compilation = compile_file(source, output, optimize)

        if compilation is None or compilation.returncode != 0:
            return False, f"Compilation failed, optimize={optimize}"

        execution = run_program(output)

        if execution is None or execution.returncode != 0:
            return False, f"Execution failed, optimize={optimize}"

        if execution.stdout != expected_output:
            return False, f"Output mismatch, optimize={optimize}"

    return True, ""


def check_ok_test(source, output):
    results = []

    for optimize in (False, True):
        compilation = compile_file(source, output, optimize)

        if compilation is None or compilation.returncode != 0:
            return False, f"Compilation failed, optimize={optimize}"

        execution = run_program(output)

        if execution is None:
            return False, "Execution timed out"

        results.append((
            execution.returncode,
            execution.stdout,
            execution.stderr
        ))

    return results[0] == results[1], "Different execution results"


def check_err_test(source, output):
    results = []

    for optimize in (False, True):
        compilation = compile_file(source, output, optimize)

        if compilation is None:
            return False, "Compilation timed out"

        results.append((
            compilation.returncode,
            compilation.stderr
        ))

    valid = results[0] == results[1] and results[0][0] != 0
    return valid, "Different compilation errors"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["all", "opt", "old"],
        default="all"
    )
    args = parser.parse_args()

    passed = 0
    total = 0

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "output.ll"

        groups = []

        if args.mode in ("all", "opt"):
            groups.append(("OPT", ROOT / "tests/opt", check_opt_test))

        if args.mode in ("all", "old"):
            groups.append(("OK", ROOT / "tests/ok", check_ok_test))
            groups.append(("ERR", ROOT / "tests/err", check_err_test))

        for label, folder, checker in groups:
            tests = sorted(folder.glob("*.txt"))

            for source in tests:
                total += 1

                try:
                    success, message = checker(source, output)
                except (OSError, ValueError) as error:
                    success, message = False, str(error)

                if success:
                    passed += 1
                    print(f"PASS {label} {source.name}")
                else:
                    print(f"FAIL {label} {source.name}: {message}")

    print(f"\nPassed {passed}/{total}")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
