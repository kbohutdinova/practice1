import sys
import os

from llvmlite import ir
import llvmlite.binding as llvm


I32 = ir.IntType(32)
I8 = ir.IntType(8)


class CompileError(Exception):
    pass


class Token:
    def __init__(self, kind, text, line, column):
        self.kind = kind
        self.text = text
        self.line = line
        self.column = column

    def __repr__(self):
        return (
            f"Token(kind={self.kind!r}, "
            f"text={self.text!r}, "
            f"line={self.line}, "
            f"column={self.column})"
        )


KEYWORDS = {
    "i32": "keyword",
    "mut": "keyword",
    "exit": "keyword",
}


def is_alpha(b):
    return (
        ord("a") <= b <= ord("z")
        or ord("A") <= b <= ord("Z")
        or b == ord("_")
    )


def is_digit(b):
    return ord("0") <= b <= ord("9")

def lex(data: bytes):
    lines = []
    tokens = []

    state = "START"
    start = 0
    start_line = 1
    start_col = 1

    line = 1
    col = 1
    i = 0

    brace_open = False
    brace_line = 0
    brace_col = 0

    while i <= len(data):
        b = data[i] if i < len(data) else None

        if state == "START":
            if b is None:
                break

            elif b in (32, 9):
                # space or tab
                pass

            elif b == 10:
                if brace_open:
                    raise CompileError(
                        f"line {brace_line}:{brace_col}: "
                        "'{' is not closed before the end of the line"
                    )

                lines.append(tokens)
                tokens = []

                line += 1
                col = 0

            elif is_alpha(b):
                state = "IDENT"
                start = i
                start_line = line
                start_col = col

            elif is_digit(b):
                state = "NUMBER"
                start = i
                start_line = line
                start_col = col

            elif b == ord("{"):
                tokens.append(
                    Token("lbrace", "{", line, col)
                )
                brace_open = True
                brace_line = line
                brace_col = col

            elif b == ord("}"):
                tokens.append(
                    Token("rbrace", "}", line, col)
                )
                brace_open = False

            elif b in (
                ord("+"),
                ord("-"),
                ord("*"),
            ):
                tokens.append(
                    Token(
                        "operator",
                        chr(b),
                        line,
                        col,
                    )
                )

            elif b == ord(":"):
                state = "COLON"
                start_line = line
                start_col = col

            elif b == ord("="):
                raise CompileError(
                    f"line {line}:{col}: unexpected byte '='"
                )

            elif b > 127:
                raise CompileError(
                    f"line {line}:{col}: unexpected byte"
                )

            else:
                raise CompileError(
                    f"line {line}:{col}: "
                    f"unexpected byte '{chr(b)}'"
                )

        elif state == "IDENT":
            if b is not None and (
                is_alpha(b) or is_digit(b)
            ):
                pass
            else:
                word = data[start:i].decode("ascii")

                kind = KEYWORDS.get(word, "identifier")

                tokens.append(
                    Token(
                        kind,
                        word,
                        start_line,
                        start_col,
                    )
                )

                state = "START"
                continue

        elif state == "NUMBER":
            if b is not None and is_digit(b):
                pass

            elif b is not None and is_alpha(b):
                raise CompileError(
                    f"line {line}:{col}: "
                    "letter inside number"
                )

            else:
                number = data[start:i].decode("ascii")

                tokens.append(
                    Token(
                        "number",
                        number,
                        start_line,
                        start_col,
                    )
                )

                state = "START"
                continue

        elif state == "COLON":
            if b == ord("="):
                tokens.append(
                    Token(
                        "operator",
                        ":=",
                        start_line,
                        start_col,
                    )
                )

                state = "START"

            else:
                raise CompileError(
                    f"line {start_line}:{start_col}: "
                    "':' must be followed by '='"
                )

        i += 1
        col += 1

    if brace_open:
        raise CompileError(
            f"line {brace_line}:{brace_col}: "
            "'{' is not closed before the end of the line"
        )

    if tokens:
        lines.append(tokens)

    return lines

def token_error(token, message):
    raise CompileError(
        f"line {token.line}:{token.column}: {message}"
    )


def get_token_value(token, builder, symbols):
    if token.kind == "number":
        return ir.Constant(I32, int(token.text))

    if token.kind == "identifier":
        if token.text not in symbols:
            token_error(
                token,
                f"variable '{token.text}' is used before its declaration"
            )

        ptr = symbols[token.text]["ptr"]

        return builder.load(
            ptr,
            name=f"load_{token.text}"
        )

    token_error(
        token,
        f"expected number or variable, got '{token.text}'"
    )

def parse_expression(tokens, builder, symbols):
    if len(tokens) == 1:
        return get_token_value(
            tokens[0],
            builder,
            symbols
        )

    if len(tokens) == 3:
        left_token = tokens[0]
        op_token = tokens[1]
        right_token = tokens[2]

        if op_token.kind != "operator":
            token_error(
                op_token,
                "expected arithmetic operator"
            )

        if op_token.text not in ("+", "-", "*"):
            token_error(
                op_token,
                f"invalid operator '{op_token.text}'"
            )

        left = get_token_value(
            left_token,
            builder,
            symbols
        )

        right = get_token_value(
            right_token,
            builder,
            symbols
        )

        if op_token.text == "+":
            return builder.add(left, right)

        if op_token.text == "-":
            return builder.sub(left, right)

        return builder.mul(left, right)

    token_error(
        tokens[0],
        "invalid expression"
    )

def compile_program(token_lines, output_path):
    module = ir.Module(name="practice2")
    module.triple = llvm.get_default_triple()

    main_type = ir.FunctionType(I32, [])
    main = ir.Function(
        module,
        main_type,
        name="main"
    )

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

    fmt_type = ir.ArrayType(
        I8,
        len(text)
    )

    fmt = ir.GlobalVariable(
        module,
        fmt_type,
        name="fmt"
    )

    fmt.linkage = "private"
    fmt.global_constant = True

    fmt.initializer = ir.Constant(
        fmt_type,
        bytearray(text)
    )

    symbols = {}
    found_exit = False

    for tokens in token_lines:
        if not tokens:
            continue
        if found_exit:
            token_error(
                tokens[0],
                "code after exit"
            )

        first = tokens[0]

        # declaration:
        # i32 x{5}
        # i32 mut y{10}

        if first.text == "i32":
            index = 1
            mutable = False

            if (
                index < len(tokens)
                and tokens[index].text == "mut"
            ):
                mutable = True
                index += 1

            if index >= len(tokens):
                token_error(
                    first,
                    "expected variable name"
                )

            name_token = tokens[index]

            if name_token.kind != "identifier":
                token_error(
                    name_token,
                    "expected variable name"
                )

            name = name_token.text

            if name in symbols:
                token_error(
                    name_token,
                    f"variable '{name}' already declared"
                )

            index += 1

            if (
                index >= len(tokens)
                or tokens[index].kind != "lbrace"
            ):
                token_error(
                    name_token,
                    f"variable '{name}' needs an initialiser in {{}}"
                )

            lbrace = tokens[index]
            index += 1

            expr_tokens = []

            while (
                index < len(tokens)
                and tokens[index].kind != "rbrace"
            ):
                expr_tokens.append(tokens[index])
                index += 1

            if index >= len(tokens):
                token_error(
                    lbrace,
                    "'{' is not closed"
                )

            if not expr_tokens:
                token_error(
                    lbrace,
                    "empty initialiser"
                )

            index += 1

            if index != len(tokens):
                token_error(
                    tokens[index],
                    "extra tokens after declaration"
                )

            value = parse_expression(
                expr_tokens,
                builder,
                symbols
            )

            ptr = builder.alloca(
                I32,
                name=name
            )

            builder.store(
                value,
                ptr
            )

            symbols[name] = {
                "ptr": ptr,
                "mutable": mutable,
            }

            continue

        # exit x
        # exit 42

        if first.text == "exit":
            if found_exit:
                token_error(
                    first,
                    "code after exit"
                )

            if len(tokens) != 2:
                token_error(
                    first,
                    "invalid exit statement"
                )

            value = get_token_value(
                tokens[1],
                builder,
                symbols
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
            continue
        # assignment:
        # y := 5
        # y := x + 3

        if (
            len(tokens) >= 3
            and tokens[0].kind == "identifier"
            and tokens[1].text == ":="
        ):
            name_token = tokens[0]
            name = name_token.text

            if name not in symbols:
                token_error(
                    name_token,
                    f"variable '{name}' is used before its declaration"
                )

            if not symbols[name]["mutable"]:
                token_error(
                    name_token,
                    f"cannot assign to '{name}': it is not mut"
                )

            expr_tokens = tokens[2:]

            value = parse_expression(
                expr_tokens,
                builder,
                symbols
            )

            builder.store(
                value,
                symbols[name]["ptr"]
            )

            continue

        token_error(
            first,
            "invalid statement"
        )

    if not found_exit:
        last_line = 1

        for line_tokens in token_lines:
            if line_tokens:
                last_line = line_tokens[0].line

        raise CompileError(
            f"line {last_line}:1: program has no exit statement"
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

    try:
        with open(source_path, "rb") as f:
            data = f.read()

        token_lines = lex(data)

        compile_program(
            token_lines,
            output_path
        )

    except CompileError as e:
        if os.path.exists(output_path):
            os.remove(output_path)

        print(
            f"compilation error: {e}",
            file=sys.stderr
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
