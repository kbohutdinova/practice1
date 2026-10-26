# Languages and Compilers — Practice 8

This compiler is implemented in Python using llvmlite.ir to generate LLVM IR.

## Features

The compiler supports features from previous practices:
- i32, i64, bool and struct types
- const and mut variables
- arithmetic and comparison expressions
- if/else and while statements
- global functions and recursion
- structs, fields and member functions
- chained member calls
- read() and print()

Practice 8 adds:
- Callable objects using a `call` member function
- Callable struct fields
- Lambda declarations with capture lists
- Captures by value
- Nested lambdas and lambdas inside loops
- Semantic rewriting of lambdas into structs
- Mutable captures using `[mut name]`
- `--ast-checked` output
- Semantic errors with line:column positions

## Requirements

- Python 3
- llvmlite
- LLVM `lli`

## Compile and run

```bash
python3 compiler.py input.txt output.ll
lli output.ll
```

