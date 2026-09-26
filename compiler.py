import os
import sys

from llvmlite import ir
import llvmlite.binding as llvm


I1 = ir.IntType(1)
I32 = ir.IntType(32)
I64 = ir.IntType(64)
I8 = ir.IntType(8)

INT_TYPES = ("i32", "i64")


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


KEYWORDS = {
    "i32",
    "i64",
    "bool",
    "mut",
    "exit",
    "true",
    "false",
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

            if b in (32, 9):
                i += 1
                col += 1
                continue

            if b == 10:
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
                tokens.append(
                    Token("lbrace", "{", line, col)
                )

                brace_open = True
                brace_line = line
                brace_col = col

                i += 1
                col += 1
                continue

            if b == ord("}"):
                tokens.append(
                    Token("rbrace", "}", line, col)
                )

                brace_open = False

                i += 1
                col += 1
                continue

            if b in (
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
                state = "EQUAL"
                start_line = line
                start_col = col

                i += 1
                col += 1
                continue

            if b == ord("!"):
                state = "BANG"
                start_line = line
                start_col = col

                i += 1
                col += 1
                continue

            if b > 127:
                raise CompileError(
                    f"line {line}:{col}: unexpected byte"
                )

            raise CompileError(
                f"line {line}:{col}: "
                f"unexpected byte '{chr(b)}'"
            )

        elif state == "IDENT":
            if (
                b is not None
                and (
                    is_alpha(b)
                    or is_digit(b)
                )
            ):
                i += 1
                col += 1
                continue

            word = data[start:i].decode("ascii")

            kind = (
                "keyword"
                if word in KEYWORDS
                else "identifier"
            )

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
            if (
                b is not None
                and is_digit(b)
            ):
                i += 1
                col += 1
                continue

            if (
                b is not None
                and is_alpha(b)
            ):
                raise CompileError(
                    f"line {line}:{col}: "
                    "letter inside number"
                )

            number = data[start:i].decode(
                "ascii"
            )

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

                i += 1
                col += 1
                continue

            raise CompileError(
                f"line {start_line}:{start_col}: "
                "':' must be followed by '='"
            )

        elif state == "EQUAL":
            if b == ord("="):
                tokens.append(
                    Token(
                        "operator",
                        "==",
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
                "expected '==' "
                "(a single '=' is not an operator)"
            )

        elif state == "BANG":
            if b == ord("="):
                tokens.append(
                    Token(
                        "operator",
                        "!=",
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
                "expected '!=' "
                "(a single '!' is not an operator)"
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
        f"line {token.line}:{token.column}: "
        f"{message}"
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
    def __init__(
        self,
        statements,
        exit_node,
    ):
        super().__init__(1, 1)
        self.statements = statements
        self.exit_node = exit_node

    def dump(self, indent=0):
        lines = [
            " " * indent + "Program"
        ]

        for stmt in self.statements:
            lines.extend(
                stmt.dump(indent + 2)
            )

        lines.extend(
            self.exit_node.dump(
                indent + 2
            )
        )

        return lines


class StmtNode(Node):
    pass


class DeclNode(StmtNode):
    def __init__(
        self,
        line,
        col,
        name,
        type_name,
        mutable,
        init,
    ):
        super().__init__(line, col)

        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.init = init

        # CodeGen fills this after semantic checking.
        self.ptr = None

    def dump(self, indent=0):
        kind = (
            "mut"
            if self.mutable
            else "const"
        )

        lines = [
            " " * indent
            + f"Decl {self.name} "
            + f"{self.type_name} "
            + f"{kind}"
        ]

        lines.extend(
            self.init.dump(indent + 2)
        )

        return lines


class AssignNode(StmtNode):
    def __init__(
        self,
        line,
        col,
        name,
        value,
    ):
        super().__init__(line, col)

        self.name = name
        self.value = value

        # SemanticChecker resolves this.
        self.decl = None

    def dump(self, indent=0):
        lines = [
            " " * indent
            + f"Assign {self.name}"
        ]

        lines.extend(
            self.value.dump(indent + 2)
        )

        return lines


class ExitNode(Node):
    def __init__(
        self,
        line,
        col,
        value,
    ):
        super().__init__(line, col)

        self.value = value

    def dump(self, indent=0):
        lines = [
            " " * indent + "Exit"
        ]

        lines.extend(
            self.value.dump(indent + 2)
        )

        return lines


class ExprNode(Node):
    def __init__(
        self,
        line,
        col,
    ):
        super().__init__(line, col)

        # SemanticChecker fills this.
        self.type = None


class BinOpNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        op,
        left,
        right,
    ):
        super().__init__(line, col)

        self.op = op
        self.left = left
        self.right = right

    def dump(self, indent=0):
        lines = [
            " " * indent
            + f"BinOp {self.op}"
        ]

        lines.extend(
            self.left.dump(indent + 2)
        )

        lines.extend(
            self.right.dump(indent + 2)
        )

        return lines


class VarNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        name,
    ):
        super().__init__(line, col)

        self.name = name

        # SemanticChecker resolves this.
        self.decl = None

    def dump(self, indent=0):
        return [
            " " * indent
            + f"Var {self.name}"
        ]


class ConstNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        value,
    ):
        super().__init__(line, col)

        self.value = value

    def dump(self, indent=0):
        return [
            " " * indent
            + f"Const {self.value}"
        ]


class BoolNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        value,
    ):
        super().__init__(line, col)

        self.value = value

    def dump(self, indent=0):
        text = (
            "true"
            if self.value
            else "false"
        )

        return [
            " " * indent
            + f"Bool {text}"
        ]


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
            self.error_at_end(
                "unexpected end of line"
            )

        self.pos += 1
        return tok

    def error_at_end(
        self,
        message,
    ):
        raise CompileError(
            f"line {self.current_line}:"
            f"{self.end_col}: "
            f"{message}"
        )

    def expect_text(
        self,
        text,
        message=None,
    ):
        tok = self.peek()

        if message is None:
            message = (
                f"expected '{text}'"
            )

        if tok is None:
            self.error_at_end(
                message
            )

        if tok.text != text:
            token_error(
                tok,
                message,
            )

        return self.eat()

    def expect_kind(
        self,
        kind,
        what,
    ):
        tok = self.peek()

        if tok is None:
            self.error_at_end(
                f"expected {what}"
            )

        if tok.kind != kind:
            token_error(
                tok,
                f"expected {what}, "
                f"got '{tok.text}'",
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

            self.current_line = (
                tokens[0].line
            )

            self.end_col = (
                tokens[-1].column
                + len(
                    tokens[-1].text
                )
            )

            last_line = (
                self.current_line
            )

            last_end_col = (
                self.end_col
            )

            if exit_node is not None:
                token_error(
                    tokens[0],
                    "code after exit",
                )

            first = self.peek()

            if first.text == "exit":
                exit_node = (
                    self.parse_exit()
                )
            else:
                statements.append(
                    self.parse_statement()
                )

            if self.peek() is not None:
                token_error(
                    self.peek(),
                    f"unexpected "
                    f"'{self.peek().text}' "
                    "after the statement",
                )

        if exit_node is None:
            raise CompileError(
                f"line {last_line}:"
                f"{last_end_col}: "
                "program has no exit statement"
            )

        return ProgramNode(
            statements,
            exit_node,
        )

    def parse_statement(self):
        tok = self.peek()

        if tok is None:
            self.error_at_end(
                "expected a statement"
            )

        if tok.text in (
            "i32",
            "i64",
            "bool",
        ):
            return self.parse_decl()

        if tok.kind == "identifier":
            return self.parse_assign()

        token_error(
            tok,
            f"cannot start a statement "
            f"with '{tok.text}'",
        )

    def parse_decl(self):
        type_tok = self.eat()

        mutable = False

        if (
            self.peek() is not None
            and self.peek().text
            == "mut"
        ):
            self.eat()
            mutable = True

        name = self.expect_kind(
            "identifier",
            "a variable name",
        )

        if self.peek() is None:
            token_error(
                name,
                f"variable "
                f"'{name.text}' "
                "needs an initialiser "
                "in {}",
            )

        if self.peek().text != "{":
            token_error(
                self.peek(),
                f"variable "
                f"'{name.text}' "
                "needs an initialiser "
                "in {}",
            )

        self.eat()

        if self.peek() is None:
            self.error_at_end(
                "expected a constant "
                "or a variable"
            )

        init = self.parse_expr()

        self.expect_text(
            "}",
            "expected '}' "
            "after initialiser",
        )

        return DeclNode(
            name.line,
            name.column,
            name.text,
            type_tok.text,
            mutable,
            init,
        )

    def parse_assign(self):
        name = self.expect_kind(
            "identifier",
            "a variable name",
        )

        self.expect_text(
            ":=",
            f"expected ':=' "
            f"after '{name.text}'",
        )

        if self.peek() is None:
            self.error_at_end(
                "expected a constant "
                "or a variable"
            )

        value = self.parse_expr()

        return AssignNode(
            name.line,
            name.column,
            name.text,
            value,
        )

    def parse_exit(self):
        exit_tok = (
            self.expect_text(
                "exit"
            )
        )

        if self.peek() is None:
            self.error_at_end(
                "expected a constant "
                "or a variable"
            )

        # exit accepts only a factor,
        # never an operation.
        value = self.parse_factor()

        return ExitNode(
            exit_tok.line,
            exit_tok.column,
            value,
        )

    def parse_expr(self):
        node = self.parse_arith()

        # Only one comparison is allowed.
        if (
            self.peek() is not None
            and self.peek().kind
            == "operator"
            and self.peek().text
            in ("==", "!=")
        ):
            op = self.eat()

            right = (
                self.parse_arith()
            )

            node = BinOpNode(
                op.line,
                op.column,
                op.text,
                node,
                right,
            )

        return node

    def parse_arith(self):
        node = self.parse_term()

        while (
            self.peek() is not None
            and self.peek().kind
            == "operator"
            and self.peek().text
            in ("+", "-")
        ):
            op = self.eat()

            right = (
                self.parse_term()
            )

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
            and self.peek().kind
            == "operator"
            and self.peek().text
            == "*"
        ):
            op = self.eat()

            right = (
                self.parse_factor()
            )

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
                "expected a constant "
                "or a variable, "
                "found end of line"
            )

        if tok.kind == "number":
            self.eat()

            return ConstNode(
                tok.line,
                tok.column,
                int(tok.text),
            )

        if tok.text == "true":
            self.eat()

            return BoolNode(
                tok.line,
                tok.column,
                True,
            )

        if tok.text == "false":
            self.eat()

            return BoolNode(
                tok.line,
                tok.column,
                False,
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
            "expected a constant "
            "or a variable, "
            f"got '{tok.text}'",
        )


# ============================================================
# SEMANTIC CHECKER
# ============================================================


class SemanticChecker:
    def __init__(self):
        self.symbols = {}

    def check(self, program):
        self.visit_program(
            program
        )

    def visit_program(self, node):
        for stmt in node.statements:
            self.visit_stmt(stmt)

        self.visit_exit(
            node.exit_node
        )

    def visit_stmt(self, node):
        if isinstance(
            node,
            DeclNode,
        ):
            self.visit_decl(node)
            return

        if isinstance(
            node,
            AssignNode,
        ):
            self.visit_assign(node)
            return

        raise RuntimeError(
            "unknown statement node: "
            f"{type(node).__name__}"
        )

    def visit_decl(self, node):
        # Old Practice 3 check:
        # declaration only once.
        if node.name in self.symbols:
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"variable "
                f"'{node.name}' "
                "already declared"
            )

        # Important:
        # check initializer BEFORE
        # adding this declaration.
        self.visit_expr(
            node.init
        )

        # Required special error:
        # a large constant directly
        # placed into i32.
        if (
            isinstance(
                node.init,
                ConstNode,
            )
            and node.type_name
            == "i32"
            and node.init.type
            == "i64"
        ):
            raise CompileError(
                f"line "
                f"{node.init.line}:"
                f"{node.init.col}: "
                f"constant "
                f"{node.init.value} "
                "does not fit in i32"
            )

        self.check_assignable(
            node.init,
            node.type_name,
            node,
            f"initialise "
            f"'{node.name}'",
        )

        self.symbols[
            node.name
        ] = node

    def visit_assign(self, node):
        # Old Practice 3 check:
        # used before declaration.
        if (
            node.name
            not in self.symbols
        ):
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"variable "
                f"'{node.name}' "
                "is used before "
                "its declaration"
            )

        decl = self.symbols[
            node.name
        ]

        # Old Practice 3 check:
        # assignment only to mut.
        if not decl.mutable:
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"cannot assign to "
                f"'{node.name}': "
                "it is not mut"
            )

        node.decl = decl

        self.visit_expr(
            node.value
        )

        self.check_assignable(
            node.value,
            decl.type_name,
            node,
            f"assign to "
            f"'{node.name}'",
        )

    def visit_exit(self, node):
        # Parser already guarantees
        # exit receives only a factor.
        self.visit_expr(
            node.value
        )

    def visit_expr(self, node):
        if isinstance(
            node,
            ConstNode,
        ):
            return (
                self.visit_const(
                    node
                )
            )

        if isinstance(
            node,
            BoolNode,
        ):
            return (
                self.visit_bool(
                    node
                )
            )

        if isinstance(
            node,
            VarNode,
        ):
            return (
                self.visit_var(
                    node
                )
            )

        if isinstance(
            node,
            BinOpNode,
        ):
            return (
                self.visit_binop(
                    node
                )
            )

        raise RuntimeError(
            "unknown expression node: "
            f"{type(node).__name__}"
        )

    def visit_const(self, node):
        # Decimal constants get the
        # narrowest type they fit.

        if (
            node.value
            <= 2147483647
        ):
            node.type = "i32"
            return node.type

        if (
            node.value
            <= 9223372036854775807
        ):
            node.type = "i64"
            return node.type

        raise CompileError(
            f"line {node.line}:"
            f"{node.col}: "
            f"constant "
            f"{node.value} "
            "does not fit in i64"
        )

    def visit_bool(self, node):
        node.type = "bool"
        return node.type

    def visit_var(self, node):
        if (
            node.name
            not in self.symbols
        ):
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"variable "
                f"'{node.name}' "
                "is used before "
                "its declaration"
            )

        node.decl = (
            self.symbols[
                node.name
            ]
        )

        node.type = (
            node.decl.type_name
        )

        return node.type

    def visit_binop(self, node):
        left_type = (
            self.visit_expr(
                node.left
            )
        )

        right_type = (
            self.visit_expr(
                node.right
            )
        )

        # Arithmetic:
        # integer only.
        if node.op in (
            "+",
            "-",
            "*",
        ):
            if (
                left_type
                not in INT_TYPES
            ):
                raise CompileError(
                    f"line {node.line}:"
                    f"{node.col}: "
                    f"cannot apply "
                    f"'{node.op}' "
                    f"to {left_type}"
                )

            if (
                right_type
                not in INT_TYPES
            ):
                raise CompileError(
                    f"line {node.line}:"
                    f"{node.col}: "
                    f"cannot apply "
                    f"'{node.op}' "
                    f"to {right_type}"
                )

            if (
                left_type == "i64"
                or right_type == "i64"
            ):
                node.type = "i64"
            else:
                node.type = "i32"

            return node.type

        # Comparisons:
        # int/int or bool/bool.
        if node.op in (
            "==",
            "!=",
        ):
            left_is_int = (
                left_type
                in INT_TYPES
            )

            right_is_int = (
                right_type
                in INT_TYPES
            )

            if (
                left_is_int
                and right_is_int
            ):
                node.type = "bool"
                return node.type

            if (
                left_type == "bool"
                and right_type
                == "bool"
            ):
                node.type = "bool"
                return node.type

            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"cannot compare "
                f"{left_type} "
                f"with "
                f"{right_type}"
            )

        raise CompileError(
            f"line {node.line}:"
            f"{node.col}: "
            f"invalid operator "
            f"'{node.op}'"
        )

    def check_assignable(
        self,
        expr,
        want,
        at,
        what,
    ):
        have = expr.type

        # Exact same type.
        if have == want:
            return

        # The only implicit conversion.
        if (
            have == "i32"
            and want == "i64"
        ):
            return

        raise CompileError(
            f"line {at.line}:"
            f"{at.col}: "
            f"cannot {what} "
            f"of type {want} "
            f"with a value "
            f"of type {have}"
        )


# ============================================================
# CODE GENERATION
# ============================================================


def llvm_type(type_name):
    if type_name == "i32":
        return I32

    if type_name == "i64":
        return I64

    if type_name == "bool":
        return I1

    raise RuntimeError(
        f"unknown type: "
        f"{type_name}"
    )


class CodeGen:
    def __init__(self):
        self.module = ir.Module(
            name="practice4"
        )

        self.module.triple = (
            llvm.get_default_triple()
        )

        main_type = (
            ir.FunctionType(
                I32,
                [],
            )
        )

        self.main = ir.Function(
            self.module,
            main_type,
            name="main",
        )

        entry = (
            self.main
            .append_basic_block(
                "entry"
            )
        )

        self.builder = (
            ir.IRBuilder(entry)
        )

        printf_type = (
            ir.FunctionType(
                I32,
                [
                    ir.PointerType(
                        I8
                    )
                ],
                var_arg=True,
            )
        )

        self.printf = (
            ir.Function(
                self.module,
                printf_type,
                name="printf",
            )
        )

        self.int_fmt = (
            self.make_string(
                "fmt_int",
                b"Program exit "
                b"with result %lld\n\0",
            )
        )

        self.bool_true = (
            self.make_string(
                "bool_true",
                b"Program exit "
                b"with result true\n\0",
            )
        )

        self.bool_false = (
            self.make_string(
                "bool_false",
                b"Program exit "
                b"with result false\n\0",
            )
        )

    def make_string(
        self,
        name,
        text,
    ):
        string_type = (
            ir.ArrayType(
                I8,
                len(text),
            )
        )

        global_value = (
            ir.GlobalVariable(
                self.module,
                string_type,
                name=name,
            )
        )

        global_value.linkage = (
            "private"
        )

        global_value.global_constant = (
            True
        )

        global_value.initializer = (
            ir.Constant(
                string_type,
                bytearray(text),
            )
        )

        return global_value

    def string_ptr(
        self,
        global_value,
    ):
        return (
            self.builder.bitcast(
                global_value,
                ir.PointerType(I8),
            )
        )

    def generate(
        self,
        program,
    ):
        self.visit_program(
            program
        )

        return str(
            self.module
        )

    def visit_program(
        self,
        node,
    ):
        for stmt in node.statements:
            self.visit_stmt(stmt)

        self.visit_exit(
            node.exit_node
        )

    def visit_stmt(
        self,
        node,
    ):
        if isinstance(
            node,
            DeclNode,
        ):
            self.visit_decl(node)
            return

        if isinstance(
            node,
            AssignNode,
        ):
            self.visit_assign(node)
            return

        raise RuntimeError(
            "unknown statement node: "
            f"{type(node).__name__}"
        )

    def visit_decl(
        self,
        node,
    ):
        value = (
            self.visit_expr(
                node.init
            )
        )

        value = self.coerce(
            value,
            node.init.type,
            node.type_name,
        )

        ptr = (
            self.builder.alloca(
                llvm_type(
                    node.type_name
                ),
                name=node.name,
            )
        )

        self.builder.store(
            value,
            ptr,
        )

        node.ptr = ptr

    def visit_assign(
        self,
        node,
    ):
        value = (
            self.visit_expr(
                node.value
            )
        )

        value = self.coerce(
            value,
            node.value.type,
            node.decl.type_name,
        )

        self.builder.store(
            value,
            node.decl.ptr,
        )

    def visit_exit(
        self,
        node,
    ):
        value = (
            self.visit_expr(
                node.value
            )
        )

        if (
            node.value.type
            in INT_TYPES
        ):
            # printf uses i64 for
            # all integer exits.
            value = self.coerce(
                value,
                node.value.type,
                "i64",
            )

            self.builder.call(
                self.printf,
                [
                    self.string_ptr(
                        self.int_fmt
                    ),
                    value,
                ],
            )

        elif (
            node.value.type
            == "bool"
        ):
            true_ptr = (
                self.string_ptr(
                    self.bool_true
                )
            )

            false_ptr = (
                self.string_ptr(
                    self.bool_false
                )
            )

            # No branches yet.
            # select chooses the
            # correct string.
            text_ptr = (
                self.builder.select(
                    value,
                    true_ptr,
                    false_ptr,
                    name="bool_text",
                )
            )

            self.builder.call(
                self.printf,
                [text_ptr],
            )

        else:
            raise RuntimeError(
                f"unknown exit type: "
                f"{node.value.type}"
            )

        self.builder.ret(
            ir.Constant(
                I32,
                0,
            )
        )

    def visit_expr(
        self,
        node,
    ):
        if isinstance(
            node,
            ConstNode,
        ):
            return ir.Constant(
                llvm_type(
                    node.type
                ),
                node.value,
            )

        if isinstance(
            node,
            BoolNode,
        ):
            return ir.Constant(
                I1,
                (
                    1
                    if node.value
                    else 0
                ),
            )

        if isinstance(
            node,
            VarNode,
        ):
            return (
                self.builder.load(
                    node.decl.ptr,
                    name=(
                        f"load_"
                        f"{node.name}"
                    ),
                )
            )

        if isinstance(
            node,
            BinOpNode,
        ):
            left = (
                self.visit_expr(
                    node.left
                )
            )

            right = (
                self.visit_expr(
                    node.right
                )
            )

            if node.op in (
                "+",
                "-",
                "*",
            ):
                target_type = (
                    node.type
                )

                left = self.coerce(
                    left,
                    node.left.type,
                    target_type,
                )

                right = self.coerce(
                    right,
                    node.right.type,
                    target_type,
                )

                if node.op == "+":
                    return (
                        self.builder.add(
                            left,
                            right,
                        )
                    )

                if node.op == "-":
                    return (
                        self.builder.sub(
                            left,
                            right,
                        )
                    )

                return (
                    self.builder.mul(
                        left,
                        right,
                    )
                )

            if node.op in (
                "==",
                "!=",
            ):
                # Integer comparisons
                # need equal widths.
                if (
                    node.left.type
                    in INT_TYPES
                    and node.right.type
                    in INT_TYPES
                ):
                    if (
                        node.left.type
                        == "i64"
                        or node.right.type
                        == "i64"
                    ):
                        target_type = (
                            "i64"
                        )
                    else:
                        target_type = (
                            "i32"
                        )

                    left = self.coerce(
                        left,
                        node.left.type,
                        target_type,
                    )

                    right = self.coerce(
                        right,
                        node.right.type,
                        target_type,
                    )

                predicate = (
                    "=="
                    if node.op == "=="
                    else "!="
                )

                return (
                    self.builder
                    .icmp_signed(
                        predicate,
                        left,
                        right,
                        name="cmp",
                    )
                )

        raise RuntimeError(
            "unknown expression node: "
            f"{type(node).__name__}"
        )

    def coerce(
        self,
        value,
        have,
        want,
    ):
        if have == want:
            return value

        if (
            have == "i32"
            and want == "i64"
        ):
            return (
                self.builder.sext(
                    value,
                    I64,
                    name="wide",
                )
            )

        # If we reach this point,
        # SemanticChecker failed.
        raise RuntimeError(
            "semantic checker "
            "allowed invalid "
            f"conversion "
            f"{have} -> {want}"
        )


# ============================================================
# COMPILER INTERFACE
# ============================================================


def parse_source(data):
    token_lines = lex(data)

    parser = Parser(
        token_lines
    )

    program = (
        parser.parse_program()
    )

    # Semantic pass happens
    # before CodeGen exists.
    checker = (
        SemanticChecker()
    )

    checker.check(
        program
    )

    return program


def compile_program(
    program,
    output_path,
):
    codegen = CodeGen()

    ir_text = (
        codegen.generate(
            program
        )
    )

    with open(
        output_path,
        "w",
    ) as f:
        f.write(
            ir_text
        )


def print_tokens(data):
    token_lines = lex(data)

    for tokens in token_lines:
        for token in tokens:
            print(
                f"{token.text!r} "
                f"{token.kind} "
                f"{token.line}:"
                f"{token.column}"
            )


def main():
    if (
        len(sys.argv) == 3
        and sys.argv[1]
        == "--tokens"
    ):
        source_path = (
            sys.argv[2]
        )

        try:
            with open(
                source_path,
                "rb",
            ) as f:
                data = f.read()

            print_tokens(
                data
            )

        except (
            CompileError,
            OSError,
        ) as e:
            print(
                f"compilation error: "
                f"{e}",
                file=sys.stderr,
            )

            sys.exit(1)

        return

    if (
        len(sys.argv) == 3
        and sys.argv[1]
        == "--ast"
    ):
        source_path = (
            sys.argv[2]
        )

        try:
            with open(
                source_path,
                "rb",
            ) as f:
                data = f.read()

            program = (
                parse_source(
                    data
                )
            )

            for line in (
                program.dump()
            ):
                print(line)

        except (
            CompileError,
            OSError,
        ) as e:
            print(
                f"compilation error: "
                f"{e}",
                file=sys.stderr,
            )

            sys.exit(1)

        return

    if len(sys.argv) != 3:
        print(
            "usage:",
            file=sys.stderr,
        )

        print(
            "  python3 "
            "compiler.py "
            "input.txt "
            "output.ll",
            file=sys.stderr,
        )

        print(
            "  python3 "
            "compiler.py "
            "--ast input.txt",
            file=sys.stderr,
        )

        print(
            "  python3 "
            "compiler.py "
            "--tokens input.txt",
            file=sys.stderr,
        )

        sys.exit(1)

    source_path = (
        sys.argv[1]
    )

    output_path = (
        sys.argv[2]
    )

    try:
        with open(
            source_path,
            "rb",
        ) as f:
            data = f.read()

        program = (
            parse_source(data)
        )

        compile_program(
            program,
            output_path,
        )

    except (
        CompileError,
        OSError,
    ) as e:
        if os.path.exists(
            output_path
        ):
            os.remove(
                output_path
            )

        print(
            f"compilation error: "
            f"{e}",
            file=sys.stderr,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
