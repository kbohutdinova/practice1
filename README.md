# Practice 5

Practice 5 extends the compiler with:

- `i32`, `i64`, and `bool` types
- boolean literals `true` and `false`
- comparison operators `==` and `!=`
- unary boolean operator `!`
- `if` and optional `else`
- nested blocks and block scopes
- variable shadowing
- LLVM basic blocks for branches
- entry-block `alloca` instructions
- `while` loops as an additional task
- type checking and `i32 -> i64` widening
- LLVM IR generation with `llvmlite`

## Run

```bash
python3 compiler.py input.txt output.ll
lli output.ll
```

## Print AST

```bash
python3 compiler.py --ast input.txt
```

## Run Practice 5 tests

```bash
python3 check.py
```

## Run previous regression tests

```bash
python3 run_tests.py
python3 run_tests_practice3.py
python3 run_tests_practice4.py
```

Note: the old Practice 4 `single_bang` error test is expected to fail under Practice 5 because unary `!` is now valid syntax.

## mem2reg check

```bash
python3 compiler.py tests/ok/assigned_both_arms.txt output.ll
opt-18 -passes=mem2reg -S output.ll
```

The promoted IR should contain a `phi` node in the merge block.

## Bonus while example

```bash
python3 compiler.py tests/ok/while_sum.txt output.ll
lli output.ll
```

Expected output:

```text
Program exit with result 55
```
