import sys
import os
import re

from llvmlite import ir
import llvmlite.binding as llvm


I32 = ir.IntType(32)
I8 = ir.IntType(8)


def compilation_error(line_no, message, output_path):
    if os.path.exists(output_path):
        os.remove(output_path)

    print(f"compilation error: line {line_no}: {message}", file=sys.stderr)
    sys.exit(1)


def valid_name(name):
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None


def get_value(token, builder, symbols, line_no, output_path):
    if re.fullmatch(r"-?\d+", token):
        return ir.Constant(I32, int(token))

    if token not in symbols:
        compilation_error(
            line_no,
            f"undeclared variable '{token}'",
            output_path
        )

    return builder.load(symbols[token], name=f"load_{token}")


def compile_program(source_path, output_path):
    module = ir.Module(name="practice1")
    module.triple = llvm.get_default_triple()

    main_type = ir.FunctionType(I32, [])
    main = ir.Function(module, main_type, name="main")

    entry = main.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    printf_type = ir.FunctionType(
        I32,
        [ir.PointerType(I8)],
        var_arg=True
    )

    printf = ir.Function(
        module,
        printf_type,
        name="printf"
    )

    text = b"Program exit with result %d\n\0"

    fmt_type = ir.ArrayType(I8, len(text))
    fmt = ir.GlobalVariable(module, fmt_type, name="fmt")

    fmt.linkage = "private"
    fmt.global_constant = True
    fmt.initializer = ir.Constant(
        fmt_type,
        bytearray(text)
    )

    symbols = {}
    found_exit = False

    with open(source_path, "r") as f:
        lines = f.readlines()

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        if not line:
            continue

        # int x
        if line.startswith("int "):
            parts = line.split()

            if len(parts) != 2:
                compilation_error(
                    line_no,
                    "invalid declaration",
                    output_path
                )

            name = parts[1]

            if not valid_name(name):
                compilation_error(
                    line_no,
                    f"invalid variable name '{name}'",
                    output_path
                )

            if name in ("int", "exit"):
                compilation_error(
                    line_no,
                    f"reserved name '{name}'",
                    output_path
                )

            if name in symbols:
                compilation_error(
                    line_no,
                    f"variable '{name}' already declared",
                    output_path
                )

            symbols[name] = builder.alloca(
                I32,
                name=name
            )

            continue

        # exit x
        if line.startswith("exit "):
            parts = line.split()

            if len(parts) != 2:
                compilation_error(
                    line_no,
                    "invalid exit statement",
                    output_path
                )

            token = parts[1]
            value = get_value(
                token,
                builder,
                symbols,
                line_no,
                output_path
            )

            fmt_ptr = builder.bitcast(
                fmt,
                ir.PointerType(I8)
            )

            builder.call(
                printf,
                [fmt_ptr, value]
            )

            builder.ret(
                ir.Constant(I32, 0)
            )

            found_exit = True

            # exit must be last meaningful statement
            remaining = lines[line_no:]

            for rest in remaining:
                if rest.strip():
                    compilation_error(
                        line_no + 1,
                        "code after exit",
                        output_path
                    )

            break

        # assignment
        if ":=" in line:
            left, right = line.split(":=", 1)

            name = left.strip()
            expression = right.strip()

            if name not in symbols:
                compilation_error(
                    line_no,
                    f"undeclared variable '{name}'",
                    output_path
                )

            # one operation: + - *
            match = re.fullmatch(
                r"(\S+)\s*([+\-*])\s*(\S+)",
                expression
            )

            if match:
                lhs_token = match.group(1)
                op = match.group(2)
                rhs_token = match.group(3)

                lhs = get_value(
                    lhs_token,
                    builder,
                    symbols,
                    line_no,
                    output_path
                )

                rhs = get_value(
                    rhs_token,
                    builder,
                    symbols,
                    line_no,
                    output_path
                )

                if op == "+":
                    result = builder.add(lhs, rhs)
                elif op == "-":
                    result = builder.sub(lhs, rhs)
                else:
                    result = builder.mul(lhs, rhs)

            else:
                result = get_value(
                    expression,
                    builder,
                    symbols,
                    line_no,
                    output_path
                )

            builder.store(
                result,
                symbols[name]
            )

            continue

        compilation_error(
            line_no,
            f"cannot parse '{line}'",
            output_path
        )

    if not found_exit:
        compilation_error(
            len(lines),
            "no exit statement",
            output_path
        )

    with open(output_path, "w") as f:
        f.write(str(module))


def main():
    if len(sys.argv) != 3:
        print(
            "usage: python3 compiler.py input.txt output.ll",
            file=sys.stderr
        )
        sys.exit(1)

    source_path = sys.argv[1]
    output_path = sys.argv[2]

    compile_program(
        source_path,
        output_path
    )


if __name__ == "__main__":
    main()
