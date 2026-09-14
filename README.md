# Languages and Compilers Design — Practice 2

This project implements a small compiler front end with a hand-written lexer
implemented as a byte-by-byte state machine.

## Requirements

- Python 3
- llvmlite
- LLVM tools: lli, llc, clang

## Run the compiler

```bash
python3 compiler.py input.txt output.ll
```
## Run generated LLVM IR
```lli output.ll```
## Build executable
```bash llc -filetype=obj -relocation-model=pic output.ll -o output.o
clang -fPIE output.o -o program
./program ```
## Run tests
```python3 run_tests.py ```

The test suite contains valid and invalid programs for declarations,
mutable variables, arithmetic expressions, assignments, exit statements,
lexer errors, and semantic errors.
