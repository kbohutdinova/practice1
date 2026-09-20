import os
import sys

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
            f"Token(kind={self.kind!r}, text={self.text!r}, "
            f"line={self.line}, column={self.column})"
        )


KEYWORDS = {"i32", "mut", "exit"}


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

            if b in (32, 9):  # space or tab
                i += 1
                col += 1
                continue

            if b == 10:  # newline
                if brace_open:
                    raise CompileError(
                        f"line {brace_line}:{brace_col}: "
                        "'{' is not closed before the end of the line"
                    )

                lines.append(tokens)
                tokens = []
                line += 1
                col = 1
                i += 1
                continue

            if is_alpha(b):
                state = "IDENT"
                start = i
                start_line = line
                start_col = col
                i += 1
                col += 1
                continue

            if is_digit(b):
                state = "NUMBER"
                start = i
                start_line = line
                start_col = col
                i += 1
                col += 1
                continue

            if b == ord("{"):
                tokens.append(Token("lbrace", "{", line, col))
                brace_open = True
                brace_line = line
                brace_col = col
                i += 1
                col += 1
                continue

            if b == ord("}"):
                tokens.append(Token("rbrace", "}", line, col))
                brace_open = False
                i += 1
                col += 1
                continue

            if b in (ord("+"), ord("-"), ord("*")):
                tokens.append(Token("operator", chr(b), line, col))
                i += 1
                col += 1
                continue

            if b == ord(":"):
                state = "COLON"
                start_line = line
                start_col = col
                i += 1
                col += 1
                continue

            if b == ord("="):
                raise CompileError(
                    f"line {line}:{col}: unexpected byte '='"
                )

            if b > 127:
                raise CompileError(
                    f"line {line}:{col}: unexpected byte"
                )

            raise CompileError(
                f"line {line}:{col}: unexpected byte '{chr(b)}'"
            )

        elif state == "IDENT":
            if b is not None and (is_alpha(b) or is_digit(b)):
                i += 1
                col += 1
                continue

            word = data[start:i].decode("ascii")
            kind = "keyword" if word in KEYWORDS else "identifier"
            tokens.append(Token(kind, word, start_line, start_col))
            state = "START"
            continue

        elif state == "NUMBER":
            if b is not None and is_digit(b):
                i += 1
                col += 1
                continue

            if b is not None and is_alpha(b):
                raise CompileError(
                    f"line {line}:{col}: letter inside number"
                )

            number = data[start:i].decode("ascii")
            tokens.append(Token("number", number, start_line, start_col))
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
                i += 1
                col += 1
                continue

            raise CompileError(
                f"line {start_line}:{start_col}: "
                "':' must be followed by '='"
            )

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


# ============================================================
# AST
# ============================================================

class Node:
    def __init__(self, line, col):
        self.line = line
        self.col = col

    def dump(self, indent=0):
        raise NotImplementedError


class ProgramNode(Node):
    def __init__(self, statements, exit_node):
        super().__init__(1, 1)
        self.statements = statements
        self.exit_node = exit_node

    def dump(self, indent=0):
        lines = [" " * indent + "Program"]

        for stmt in self.statements:
            lines.extend(stmt.dump(indent + 2))

        lines.extend(self.exit_node.dump(indent + 2))
        return lines


class StmtNode(Node):
    pass


class DeclNode(StmtNode):
    def __init__(self, line, col, name, mutable, init):
        super().__init__(line, col)
        self.name = name
        self.mutable = mutable
        self.init = init

    def dump(self, indent=0):
        kind = "mut" if self.mutable else "const"
        lines = [" " * indent + f"Decl {self.name} {kind}"]
        lines.extend(self.init.dump(indent + 2))
        return lines


class AssignNode(StmtNode):
    def __init__(self, line, col, name, value):
        super().__init__(line, col)
        self.name = name
        self.value = value

    def dump(self, indent=0):
        lines = [" " * indent + f"Assign {self.name}"]
        lines.extend(self.value.dump(indent + 2))
        return lines


class ExitNode(Node):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def dump(self, indent=0):
        lines = [" " * indent + "Exit"]
        lines.extend(self.value.dump(indent + 2))
        return lines


class ExprNode(Node):
    pass


class BinOpNode(ExprNode):
    def __init__(self, line, col, op, left, right):
        super().__init__(line, col)
        self.op = op
        self.left = left
        self.right = right

    def dump(self, indent=0):
        lines = [" " * indent + f"BinOp {self.op}"]
        lines.extend(self.left.dump(indent + 2))
        lines.extend(self.right.dump(indent + 2))
        return lines


class VarNode(ExprNode):
    def __init__(self, line, col, name):
        super().__init__(line, col)
        self.name = name

    def dump(self, indent=0):
        return [" " * indent + f"Var {self.name}"]


class ConstNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def dump(self, indent=0):
        return [" " * indent + f"Const {self.value}"]


# ============================================================
# PARSER
# ============================================================

class Parser:
    def __init__(self, lines):
        self.lines = lines
        self.toks = []
        self.pos = 0
        self.current_line = 1
        self.end_col = 1

    def peek(self):
        if self.pos < len(self.toks):
            return self.toks[self.pos]
        return None

    def eat(self):
        tok = self.peek()

        if tok is None:
            self.error_at_end("unexpected end of line")

        self.pos += 1
        return tok

    def error_at_end(self, message):
        raise CompileError(
            f"line {self.current_line}:{self.end_col}: {message}"
        )

    def expect_text(self, text, message=None):
        tok = self.peek()

        if message is None:
            message = f"expected '{text}'"

        if tok is None:
            self.error_at_end(message)

        if tok.text != text:
            token_error(tok, message)

        return self.eat()

    def expect_kind(self, kind, what):
        tok = self.peek()

        if tok is None:
            self.error_at_end(f"expected {what}")

        if tok.kind != kind:
            token_error(
                tok,
                f"expected {what}, got '{tok.text}'"
            )

        return self.eat()

    def parse_program(self):
        statements = []
        exit_node = None

        last_line = 1
        last_end_col = 1

        for tokens in self.lines:
            if not tokens:
                continue

            self.toks = tokens
            self.pos = 0
            self.current_line = tokens[0].line
            self.end_col = tokens[-1].column + len(tokens[-1].text)

            last_line = self.current_line
            last_end_col = self.end_col

            if exit_node is not None:
                token_error(tokens[0], "code after exit")

            first = self.peek()

            if first.text == "exit":
                exit_node = self.parse_exit()
            else:
                statements.append(self.parse_statement())

            if self.peek() is not None:
                token_error(
                    self.peek(),
                    f"unexpected '{self.peek().text}' after the statement"
                )

        if exit_node is None:
            raise CompileError(
                f"line {last_line}:{last_end_col}: "
                "program has no exit statement"
            )

        return ProgramNode(statements, exit_node)

    def parse_statement(self):
        tok = self.peek()

        if tok is None:
            self.error_at_end("expected a statement")

        if tok.text == "i32":
            return self.parse_decl()

        if tok.kind == "identifier":
            return self.parse_assign()

        token_error(
            tok,
            f"cannot start a statement with '{tok.text}'"
        )

    def parse_decl(self):
        self.expect_text("i32")

        mutable = False

        if self.peek() is not None and self.peek().text == "mut":
            self.eat()
            mutable = True

        name = self.expect_kind(
            "identifier",
            "a variable name"
        )

        if self.peek() is None:
            token_error(
                name,
                f"variable '{name.text}' needs an initialiser in {{}}"
            )

        if self.peek().text != "{":
            token_error(
                self.peek(),
                f"variable '{name.text}' needs an initialiser in {{}}"
            )

        self.eat()

        if self.peek() is None:
            self.error_at_end(
                "expected a constant or a variable"
            )

        init = self.parse_expr()

        self.expect_text(
            "}",
            "expected '}' after initialiser"
        )

        return DeclNode(
            name.line,
            name.column,
            name.text,
            mutable,
            init,
        )

    def parse_assign(self):
        name = self.expect_kind(
            "identifier",
            "a variable name"
        )

        self.expect_text(
            ":=",
            f"expected ':=' after '{name.text}'"
        )

        if self.peek() is None:
            self.error_at_end(
                "expected a constant or a variable"
            )

        value = self.parse_expr()

        return AssignNode(
            name.line,
            name.column,
            name.text,
            value,
        )

    def parse_exit(self):
        exit_tok = self.expect_text("exit")

        if self.peek() is None:
            self.error_at_end(
                "expected a constant or a variable"
            )

        value = self.parse_factor()

        return ExitNode(
            exit_tok.line,
            exit_tok.column,
            value,
        )

    def parse_expr(self):
        node = self.parse_term()

        while (
            self.peek() is not None
            and self.peek().kind == "operator"
            and self.peek().text in ("+", "-")
        ):
            op = self.eat()
            right = self.parse_term()

            node = BinOpNode(
                op.line,
                op.column,
                op.text,
                node,
                right,
            )

        return node

    def parse_term(self):
        node = self.parse_factor()

        while (
            self.peek() is not None
            and self.peek().kind == "operator"
            and self.peek().text == "*"
        ):
            op = self.eat()
            right = self.parse_factor()

            node = BinOpNode(
                op.line,
                op.column,
                op.text,
                node,
                right,
            )

        return node

    def parse_factor(self):
        tok = self.peek()

        if tok is None:
            self.error_at_end(
                "expected a constant or a variable, found end of line"
            )

        if tok.kind == "number":
            self.eat()
            return ConstNode(
                tok.line,
                tok.column,
                int(tok.text),
            )

        if tok.kind == "identifier":
            self.eat()
            return VarNode(
                tok.line,
                tok.column,
                tok.text,
            )

        token_error(
            tok,
            f"expected a constant or a variable, got '{tok.text}'"
        )


# ============================================================
# CODE GENERATION
# ============================================================

class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="practice3")
        self.module.triple = llvm.get_default_triple()

        main_type = ir.FunctionType(I32, [])
        self.main = ir.Function(
            self.module,
            main_type,
            name="main"
        )

        entry = self.main.append_basic_block("entry")
        self.builder = ir.IRBuilder(entry)

        printf_type = ir.FunctionType(
            I32,
            [ir.PointerType(I8)],
            var_arg=True
        )

        self.printf = ir.Function(
            self.module,
            printf_type,
            name="printf"
        )

        text = b"Program exit with result %d\n\0"
        fmt_type = ir.ArrayType(I8, len(text))

        self.fmt = ir.GlobalVariable(
            self.module,
            fmt_type,
            name="fmt"
        )

        self.fmt.linkage = "private"
        self.fmt.global_constant = True
        self.fmt.initializer = ir.Constant(
            fmt_type,
            bytearray(text)
        )

        self.symbols = {}

    def generate(self, program):
        self.visit_program(program)
        return str(self.module)

    def visit_program(self, node):
        for stmt in node.statements:
            self.visit_stmt(stmt)

        self.visit_exit(node.exit_node)

    def visit_stmt(self, node):
        if isinstance(node, DeclNode):
            self.visit_decl(node)
            return

        if isinstance(node, AssignNode):
            self.visit_assign(node)
            return

        raise RuntimeError(
            f"unknown statement node: {type(node).__name__}"
        )

    def visit_decl(self, node):
        if node.name in self.symbols:
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"variable '{node.name}' already declared"
            )

        value = self.visit_expr(node.init)

        ptr = self.builder.alloca(
            I32,
            name=node.name
        )

        self.builder.store(value, ptr)

        self.symbols[node.name] = {
            "ptr": ptr,
            "mutable": node.mutable,
        }

    def visit_assign(self, node):
        if node.name not in self.symbols:
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"variable '{node.name}' is used before its declaration"
            )

        if not self.symbols[node.name]["mutable"]:
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"cannot assign to '{node.name}': it is not mut"
            )

        value = self.visit_expr(node.value)

        self.builder.store(
            value,
            self.symbols[node.name]["ptr"]
        )

    def visit_exit(self, node):
        value = self.visit_expr(node.value)

        fmt_ptr = self.builder.bitcast(
            self.fmt,
            ir.PointerType(I8)
        )

        self.builder.call(
            self.printf,
            [fmt_ptr, value]
        )

        self.builder.ret(
            ir.Constant(I32, 0)
        )

    def visit_expr(self, node):
        if isinstance(node, ConstNode):
            return ir.Constant(I32, node.value)

        if isinstance(node, VarNode):
            if node.name not in self.symbols:
                raise CompileError(
                    f"line {node.line}:{node.col}: "
                    f"variable '{node.name}' is used before its declaration"
                )

            ptr = self.symbols[node.name]["ptr"]

            return self.builder.load(
                ptr,
                name=f"load_{node.name}"
            )

        if isinstance(node, BinOpNode):
            left = self.visit_expr(node.left)
            right = self.visit_expr(node.right)

            if node.op == "+":
                return self.builder.add(left, right)

            if node.op == "-":
                return self.builder.sub(left, right)

            if node.op == "*":
                return self.builder.mul(left, right)

            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"invalid operator '{node.op}'"
            )

        raise RuntimeError(
            f"unknown expression node: {type(node).__name__}"
        )


def parse_source(data):
    token_lines = lex(data)
    parser = Parser(token_lines)
    return parser.parse_program()


def compile_program(program, output_path):
    codegen = CodeGen()
    ir_text = codegen.generate(program)

    with open(output_path, "w") as f:
        f.write(ir_text)


def print_tokens(data):
    token_lines = lex(data)

    for tokens in token_lines:
        for token in tokens:
            print(
                f"{token.text!r} "
                f"{token.kind} "
                f"{token.line}:{token.column}"
            )


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--tokens":
        source_path = sys.argv[2]

        try:
            with open(source_path, "rb") as f:
                data = f.read()

            print_tokens(data)

        except (CompileError, OSError) as e:
            print(
                f"compilation error: {e}",
                file=sys.stderr
            )
            sys.exit(1)

        return

    if len(sys.argv) == 3 and sys.argv[1] == "--ast":
        source_path = sys.argv[2]

        try:
            with open(source_path, "rb") as f:
                data = f.read()

            program = parse_source(data)

            for line in program.dump():
                print(line)

        except (CompileError, OSError) as e:
            print(
                f"compilation error: {e}",
                file=sys.stderr
            )
            sys.exit(1)

        return

    if len(sys.argv) != 3:
        print(
            "usage:",
            file=sys.stderr
        )
        print(
            "  python3 compiler.py input.txt output.ll",
            file=sys.stderr
        )
        print(
            "  python3 compiler.py --ast input.txt",
            file=sys.stderr
        )
        print(
            "  python3 compiler.py --tokens input.txt",
            file=sys.stderr
        )
        sys.exit(1)

    source_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        with open(source_path, "rb") as f:
            data = f.read()

        program = parse_source(data)

        compile_program(
            program,
            output_path
        )

    except (CompileError, OSError) as e:
        if os.path.exists(output_path):
            os.remove(output_path)

        print(
            f"compilation error: {e}",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
