import glob
import os
import re
import subprocess
import sys

passed = failed = 0
output = '/tmp/practice8_test.ll'

def run(path, success):
    global passed, failed
    expected = open(path.replace('.txt', '.expected'), encoding='utf-8').read().strip()
    result = subprocess.run([sys.executable, 'compiler.py', path, output], text=True, capture_output=True)
    if success:
        if result.returncode:
            got = result.stderr.strip()
        else:
            ipath = path.replace('.txt', '.in')
            stdin = open(ipath, encoding='utf-8').read() if os.path.exists(ipath) else ''
            run_result = subprocess.run(['lli', output], input=stdin, text=True, capture_output=True)
            got = run_result.stdout.strip() if run_result.returncode == 0 else run_result.stderr.strip()
        good = got == expected
    else:
        got = result.stderr.strip()
        good = result.returncode != 0 and expected in got and re.search(r'line \d+:\d+', got)
    print(('PASS' if good else 'FAIL'), path)
    if not good:
        print(' Expected:', repr(expected))
        print(' Actual:  ', repr(got))
        failed += 1
    else:
        passed += 1

for path in sorted(glob.glob('tests/ok/p8_*.txt')):
    run(path, True)
for path in sorted(glob.glob('tests/err/p8_*.txt')):
    run(path, False)
if os.path.exists(output):
    os.remove(output)
print(f'Passed {passed}/{passed + failed}')
if failed:
    sys.exit(1)
