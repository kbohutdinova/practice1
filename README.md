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


## Optimizations

Practice 9 adds the `--remove-unused` flag. The optimization runs on the checked AST before LLVM IR generation. Without the flag, the compiler works as before.

The optimization removes unused variable declarations and their assignments. It counts reads per declaration rather than per variable name, so shadowed variables are handled separately. The pass repeats until no more declarations can be removed. Initializers and assignments containing calls or `read()` are kept because they may have observable effects.

The optimization also removes unused global functions. Removing one function may make another function unused, so the process repeats. Member functions and lambdas are not removed.

A limitation of the variable-use counter is self-feeding assignments such as `k := k + 1`. The right-hand side reads `k`, so the variable is counted as used even if nothing else reads it.

### AST memory management

The compiler is implemented in Python, which uses reference counting and cyclic garbage collection. When the optimization removes a node from the AST and no strong references to it remain, Python can release the node automatically.

The optimizer does not explicitly delete AST objects. It rebuilds statement lists and removes unused functions from the program. The AST does not use a general parent pointer on every node. If parent references formed cycles with child references, reference counting alone would not release those cycles immediately, and Python's cyclic garbage collector would be needed.

A measurement was performed with `weakref.ref()` on the unused declaration `y` from `tests/opt/unused_chain.txt`.

Results:

Before optimization: True
After optimization: False
After garbage collection: False

Here, `True` means the weak reference still points to a live object. `False` means the object is no longer alive. The result shows that the removed declaration was released without requiring an explicit call to `gc.collect()`.

This concerns the compiler's AST memory, not the memory of the compiled program.

### Bonus: Effect Analysis

The bonus optimization uses EffectAnalyzer to distinguish pure functions from functions with observable effects.

A function is considered effectful if it:
- calls print() or read();
- calls a mutating member function;
- contains a while loop;
- is recursive;
- calls another effectful function.

The analysis follows function dependencies until the effect information stops changing.

Unused variables initialized by pure function calls can be removed together with those calls. Variables initialized by effectful calls are preserved, even if their values are not used.

The analysis also supports member functions, callable objects and lambdas. Unknown calls are treated conservatively as effectful.

Examples:
- square() and quiet() are pure and can be removed when unused.
- loud() calls print() and must be preserved.
- A call to a mutating method such as bump() is preserved.
- Functions containing loops or recursion are preserved conservatively.

The optimization runs only when --remove-unused is enabled.
