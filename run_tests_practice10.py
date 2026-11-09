"""Practice 10: binary end-to-end sessions, prior suite, and extern error tests.

On course Ubuntu (with llc), this uses the exact three-step build in the PDF.
If llc is unavailable, clang -c -x ir provides an equivalent LLVM-IR-to-object
fallback for local verification. All IR is produced by compiler.py.
"""
import argparse
import difflib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPILER = ROOT / 'compiler.py'


def call(args, *, input_data=None):
    return subprocess.run(args, input=input_data, capture_output=True, timeout=30, cwd=ROOT)


def build(source, output, optimize, c_source=None):
    ll = output.with_suffix('.ll')
    obj = output.with_suffix('.o')
    cmd = [sys.executable, str(COMPILER)]
    if optimize:
        cmd.append('--remove-unused')
    proc = call(cmd + [str(source), str(ll)])
    if proc.returncode:
        raise RuntimeError(f'compiler failed: {source.name}: {proc.stderr.decode(errors="replace")}')
    if shutil.which('llc'):
        cmd = ['llc', '-filetype=obj', '-relocation-model=pic', str(ll), '-o', str(obj)]
    else:
        cmd = ['clang', '-x', 'ir', '-c', '-fPIC', str(ll), '-o', str(obj)]
    proc = call(cmd)
    if proc.returncode:
        raise RuntimeError('object generation failed: ' + proc.stderr.decode(errors='replace'))
    cmd = ['clang', '-fPIE', str(obj)]
    if c_source is not None:
        cmd.append(str(c_source))
    proc = call(cmd + ['-o', str(output)])
    if proc.returncode:
        raise RuntimeError('linking failed: ' + proc.stderr.decode(errors='replace'))
    return obj, ll


def check_sessions(folder, output_dir, optimize):
    passed = total = 0
    for source in sorted(folder.glob('*.txt')):
        extra = source.with_suffix('.c') if folder.name == 'ffi' else None
        if extra is not None and not extra.exists():
            extra = None
        binary = output_dir / source.stem
        try:
            build(source, binary, optimize, extra)
            inputs = sorted(folder.glob(source.stem + '.*.in'))
            if not inputs:
                raise RuntimeError('no input sessions')
            for inp in inputs:
                total += 1
                expected = inp.with_suffix('.expected').read_bytes()
                result = call([str(binary)], input_data=inp.read_bytes())
                # Exit code is #matches or integer-square-root; stdout is the contract.
                if result.stdout != expected or result.stderr:
                    actual_text = result.stdout.decode(errors='replace').splitlines(True)
                    expect_text = expected.decode(errors='replace').splitlines(True)
                    diff = ''.join(difflib.unified_diff(expect_text, actual_text, fromfile='expected', tofile='actual'))
                    print(f'FAIL {inp.relative_to(ROOT)} ({"optimized" if optimize else "normal"}): {diff or result.stderr.decode(errors="replace")}')
                else:
                    passed += 1
                    print(f'PASS {inp.relative_to(ROOT)} ({"optimized" if optimize else "normal"})')
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            total += 1
            print(f'FAIL {source.relative_to(ROOT)}: {exc}')
    return passed, total


def check_extern_errors(output_dir, optimize):
    passed = total = 0
    for source in sorted((ROOT / 'tests' / 'err').glob('p10_extern_*.txt')):
        total += 1
        cmd = [sys.executable, str(COMPILER)]
        if optimize:
            cmd.append('--remove-unused')
        result = call(cmd + [str(source), str(output_dir / 'invalid.ll')])
        expected = source.with_suffix('.expected').read_text().strip()
        actual = result.stderr.decode(errors='replace').strip()
        if result.returncode != 0 and actual == expected:
            passed += 1
            print(f'PASS {source.relative_to(ROOT)} ({"optimized" if optimize else "normal"})')
        else:
            print(f'FAIL {source.name}: expected {expected!r}, got {actual!r}')
    return passed, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--remove-unused', action='store_true')
    parser.add_argument('--skip-previous', action='store_true')
    opts = parser.parse_args()
    passed = total = 0
    with tempfile.TemporaryDirectory(prefix='practice10-') as temp:
        output = Path(temp)
        for folder in ('io', 'ffi'):
            ok, count = check_sessions(ROOT / 'tests' / folder, output, opts.remove_unused)
            passed += ok
            total += count
        ok, count = check_extern_errors(output, opts.remove_unused)
        passed += ok
        total += count
        # Verify libc-only calls in native binary; old tests also check the .ll.
        try:
            executable = output / 'p10_libc_extern'
            build(ROOT / 'tests/ok/p10_libc_extern.txt', executable, opts.remove_unused)
            result = call([str(executable)])
            expected = b'8\n10\nProgram exit with result 8\n'
            total += 1
            if result.stdout == expected and not result.stderr:
                passed += 1
                print('PASS libc abs/llabs native binary')
            else:
                print('FAIL libc abs/llabs native binary')
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            total += 1
            print('FAIL libc native binary:', exc)
        if not opts.skip_previous:
            previous = subprocess.run([sys.executable, str(ROOT / 'run_tests_practice9.py')],
                                      capture_output=True, cwd=ROOT, timeout=600)
            print(previous.stdout.decode(errors='replace'))
            if previous.returncode != 0:
                print(previous.stderr.decode(errors='replace'))
                print('FAIL Practice 9 regression tests')
                total += 1
            else:
                print('PASS Practice 9 regression tests')
                total += 1
                passed += 1
    print(f'Practice 10: Passed {passed}/{total}')
    raise SystemExit(0 if passed == total else 1)


if __name__ == '__main__':
    main()
