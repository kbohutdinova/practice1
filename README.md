## Practice 4

Practice 4 extends the compiler with:

- `i32`, `i64`, and `bool` types
- boolean literals `true` and `false`
- comparison operators `==` and `!=`
- a separate semantic checking pass
- type checking and `i32 -> i64` widening
- LLVM code generation for integers and booleans
- `sext` for widening and `icmp` for comparisons

### Run

```bash
python3 compiler.py input.txt output.ll
lli output.ll
```

### Print AST:
```  python3 compiler.py --ast input.txt
```
### Run Practice 4 tests:
```python3 run_tests_practice4.py
```
