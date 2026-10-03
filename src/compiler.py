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


# ============================================================
# TOKENS / LEXER
# ============================================================


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
    "if",
    "else",
    "while",
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

    while i <= len(data):
        b = data[i] if i < len(data) else None

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        if state == "START":
            if b is None:
                break

            if b in (32, 9):
                i += 1
                col += 1
                continue

            if b == 10:
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

            # Braces are now plain tokens.
            # The parser, not the lexer, pairs blocks.
            if b == ord("{"):
                tokens.append(
                    Token(
                        "lbrace",
                        "{",
                        line,
                        col,
                    )
                )

                i += 1
                col += 1
                continue

            if b == ord("}"):
                tokens.append(
                    Token(
                        "rbrace",
                        "}",
                        line,
                        col,
                    )
                )

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

        # ----------------------------------------------------
        # IDENTIFIER
        # ----------------------------------------------------

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

            word = data[start:i].decode(
                "ascii"
            )

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

        # ----------------------------------------------------
        # NUMBER
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # :=
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # ==
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # ! and !=
        # ----------------------------------------------------

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

            # A single ! is now a valid operator.
            #
            # Do not consume b here.
            # It must be read again by START.
            tokens.append(
                Token(
                    "operator",
                    "!",
                    start_line,
                    start_col,
                )
            )

            state = "START"
            continue

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

    def accept(self, visitor):
        method_name = (
            "visit_"
            + self.__class__.__name__
            .replace("Node", "")
            .lower()
        )

        method = getattr(
            visitor,
            method_name,
        )

        return method(self)

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
        super().__init__(
            line,
            col,
        )

        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.init = init

        # CodeGen fills this.
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
            self.init.dump(
                indent + 2
            )
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
        super().__init__(
            line,
            col,
        )

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
            self.value.dump(
                indent + 2
            )
        )

        return lines


class IfNode(StmtNode):
    def __init__(
        self,
        line,
        col,
        condition,
        then_block,
        else_block=None,
    ):
        super().__init__(
            line,
            col,
        )

        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

    def dump(self, indent=0):
        lines = [
            " " * indent + "If"
        ]

        lines.extend(
            self.condition.dump(
                indent + 2
            )
        )

        lines.extend(
            self.then_block.dump(
                indent + 2
            )
        )

        if self.else_block is not None:
            lines.extend(
                self.else_block.dump(
                    indent + 2
                )
            )

        return lines


class WhileNode(StmtNode):
    def __init__(
        self,
        line,
        col,
        condition,
        body,
    ):
        super().__init__(
            line,
            col,
        )

        self.condition = condition
        self.body = body

    def dump(self, indent=0):
        lines = [
            " " * indent + "While"
        ]

        lines.extend(
            self.condition.dump(
                indent + 2
            )
        )

        lines.extend(
            self.body.dump(
                indent + 2
            )
        )

        return lines


class BlockNode(Node):
    def __init__(
        self,
        line,
        col,
        statements,
        exit_node=None,
    ):
        super().__init__(
            line,
            col,
        )

        self.statements = statements
        self.exit_node = exit_node

    def dump(self, indent=0):
        lines = [
            " " * indent + "Block"
        ]

        for stmt in self.statements:
            lines.extend(
                stmt.dump(
                    indent + 2
                )
            )

        if self.exit_node is not None:
            lines.extend(
                self.exit_node.dump(
                    indent + 2
                )
            )

        return lines


class ExitNode(Node):
    def __init__(
        self,
        line,
        col,
        value,
    ):
        super().__init__(
            line,
            col,
        )

        self.value = value

    def dump(self, indent=0):
        lines = [
            " " * indent + "Exit"
        ]

        lines.extend(
            self.value.dump(
                indent + 2
            )
        )

        return lines


class ExprNode(Node):
    def __init__(
        self,
        line,
        col,
    ):
        super().__init__(
            line,
            col,
        )

        # SemanticChecker fills this.
        self.type = None


class NotNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        operand,
    ):
        super().__init__(
            line,
            col,
        )

        self.operand = operand

    def dump(self, indent=0):
        lines = [
            " " * indent + "Not"
        ]

        lines.extend(
            self.operand.dump(
                indent + 2
            )
        )

        return lines


class BinOpNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        op,
        left,
        right,
    ):
        super().__init__(
            line,
            col,
        )

        self.op = op
        self.left = left
        self.right = right

    def dump(self, indent=0):
        lines = [
            " " * indent
            + f"BinOp {self.op}"
        ]

        lines.extend(
            self.left.dump(
                indent + 2
            )
        )

        lines.extend(
            self.right.dump(
                indent + 2
            )
        )

        return lines


class VarNode(ExprNode):
    def __init__(
        self,
        line,
        col,
        name,
    ):
        super().__init__(
            line,
            col,
        )

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
        super().__init__(
            line,
            col,
        )

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
        super().__init__(
            line,
            col,
        )

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
    def __init__(
        self,
        lines,
    ):
        self.lines = lines

        # Cursor between source lines.
        self.line_pos = 0

        # Cursor inside current line.
        self.toks = []
        self.pos = 0

        self.current_line = 1
        self.end_col = 1

    # --------------------------------------------------------
    # Current line helpers
    # --------------------------------------------------------

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

    def line_finished(self):
        if self.peek() is not None:
            token_error(
                self.peek(),
                f"unexpected "
                f"'{self.peek().text}' "
                "after the statement",
            )

    # --------------------------------------------------------
    # Line cursor
    # --------------------------------------------------------

    def next_line(
        self,
        skip_empty=True,
    ):
        while (
            self.line_pos
            < len(self.lines)
        ):
            tokens = (
                self.lines[
                    self.line_pos
                ]
            )

            self.line_pos += 1

            if (
                not tokens
                and skip_empty
            ):
                continue

            self.toks = tokens
            self.pos = 0

            if tokens:
                self.current_line = (
                    tokens[0].line
                )

                self.end_col = (
                    tokens[-1].column
                    + len(
                        tokens[-1].text
                    )
                )
            else:
                self.current_line = (
                    self.line_pos
                )
                self.end_col = 1

            return tokens

        self.toks = []
        self.pos = 0

        return None

    def peek_nonempty_line(self):
        p = self.line_pos

        while p < len(self.lines):
            if self.lines[p]:
                return self.lines[p]

            p += 1

        return None

    # --------------------------------------------------------
    # Program
    # --------------------------------------------------------

    def parse_program(self):
        statements = []
        exit_node = None

        last_line = 1
        last_end_col = 1

        while True:
            tokens = self.next_line()

            if tokens is None:
                break

            last_line = self.current_line
            last_end_col = self.end_col

            first = self.peek()

            if first.text == "}":
                token_error(
                    first,
                    "'}' without an open block",
                )

            if first.text == "else":
                token_error(
                    first,
                    "'else' without an 'if'",
                )

            if exit_node is not None:
                token_error(
                    first,
                    "code after exit",
                )

            if first.text == "exit":
                exit_node = (
                    self.parse_exit()
                )

                self.line_finished()
                continue

            statements.append(
                self.parse_statement()
            )

            self.line_finished()

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

    # --------------------------------------------------------
    # Statements
    # --------------------------------------------------------

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

        if tok.text == "if":
            return self.parse_if()

        if tok.text == "while":
            return self.parse_while()

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

        # Exit keeps the Practice 4 rule:
        # it takes one factor.
        # !factor is now also a factor.
        value = self.parse_factor()

        return ExitNode(
            exit_tok.line,
            exit_tok.column,
            value,
        )

    # --------------------------------------------------------
    # if
    # --------------------------------------------------------

    def parse_if(self):
        if_tok = (
            self.expect_text(
                "if"
            )
        )

        if self.peek() is None:
            self.error_at_end(
                "expected condition "
                "after 'if'"
            )

        condition = self.parse_expr()

        # Therefore "if b {" fails
        # at the { on this line.
        self.line_finished()

        then_block = self.parse_block(
            "if"
        )

        else_block = None

        next_tokens = (
            self.peek_nonempty_line()
        )

        if (
            next_tokens is not None
            and next_tokens[0].text
            == "else"
        ):
            self.next_line()

            else_tok = (
                self.expect_text(
                    "else"
                )
            )

            if self.peek() is not None:
                token_error(
                    self.peek(),
                    f"unexpected "
                    f"'{self.peek().text}' "
                    "after 'else'",
                )

            else_block = (
                self.parse_block(
                    "else",
                    else_tok,
                )
            )

        return IfNode(
            if_tok.line,
            if_tok.column,
            condition,
            then_block,
            else_block,
        )

    # --------------------------------------------------------
    # while - bonus
    # --------------------------------------------------------

    def parse_while(self):
        while_tok = (
            self.expect_text(
                "while"
            )
        )

        if self.peek() is None:
            self.error_at_end(
                "expected condition "
                "after 'while'"
            )

        condition = self.parse_expr()

        self.line_finished()

        body = self.parse_block(
            "while"
        )

        return WhileNode(
            while_tok.line,
            while_tok.column,
            condition,
            body,
        )

    # --------------------------------------------------------
    # Block
    # --------------------------------------------------------

    def parse_block(
        self,
        owner,
        owner_token=None,
    ):
        tokens = self.next_line()

        if tokens is None:
            owner_line = (
                owner_token.line
                if owner_token
                is not None
                else self.current_line
            )

            raise CompileError(
                f"line {owner_line}:1: "
                f"expected '{{' "
                f"on its own line "
                f"after '{owner}', "
                "found end of input"
            )

        first = self.peek()

        if first.text != "{":
            token_error(
                first,
                f"expected '{{' "
                f"on its own line "
                f"after '{owner}', "
                f"got '{first.text}'",
            )

        open_tok = self.eat()

        if self.peek() is not None:
            token_error(
                self.peek(),
                "unexpected token "
                "after '{'",
            )

        statements = []
        exit_node = None
        has_content = False

        while True:
            tokens = self.next_line()

            if tokens is None:
                raise CompileError(
                    f"line "
                    f"{open_tok.line}:"
                    f"{open_tok.column}: "
                    "'{' is never closed"
                )

            first = self.peek()

            # End block.
            if first.text == "}":
                self.eat()

                if self.peek() is not None:
                    token_error(
                        self.peek(),
                        "unexpected token "
                        "after '}'",
                    )

                if not has_content:
                    raise CompileError(
                        f"line "
                        f"{open_tok.line}:"
                        f"{open_tok.column}: "
                        "empty block"
                    )

                return BlockNode(
                    open_tok.line,
                    open_tok.column,
                    statements,
                    exit_node,
                )

            if first.text == "else":
                token_error(
                    first,
                    "'else' without an 'if'",
                )

            # Exit must be the last line
            # inside this block.
            if exit_node is not None:
                token_error(
                    first,
                    "statement after 'exit' "
                    "in the same block",
                )

            has_content = True

            if first.text == "exit":
                exit_node = (
                    self.parse_exit()
                )

                self.line_finished()
                continue

            statements.append(
                self.parse_statement()
            )

            self.line_finished()

    # --------------------------------------------------------
    # Expressions
    # --------------------------------------------------------

    def parse_expr(self):
        node = self.parse_arith()

        # Only one comparison is parsed.
        # A second comparison stays behind
        # and is rejected as an extra token,
        # preserving Practice 4 behaviour.
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

        # Practice 5 unary !
        #
        # ! applies only to the factor
        # immediately after it.
        if tok.text == "!":
            op = self.eat()

            operand = (
                self.parse_factor()
            )

            return NotNode(
                op.line,
                op.column,
                operand,
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
        # Global scope.
        self.scopes = [{}]

    def check(
        self,
        program,
    ):
        program.accept(self)

    # --------------------------------------------------------
    # Scope lookup
    # --------------------------------------------------------

    def lookup(
        self,
        node,
        name,
    ):
        for frame in reversed(
            self.scopes
        ):
            if name in frame:
                return frame[name]

        raise CompileError(
            f"line {node.line}:"
            f"{node.col}: "
            f"variable '{name}' "
            "is used before "
            "its declaration"
        )

    # --------------------------------------------------------
    # Statements
    # --------------------------------------------------------

    def visit_program(
        self,
        node,
    ):
        for stmt in node.statements:
            stmt.accept(self)

        node.exit_node.accept(self)

    def visit_block(
        self,
        node,
    ):
        # Every block owns a scope.
        self.scopes.append({})

        try:
            for stmt in node.statements:
                stmt.accept(self)

            if (
                node.exit_node
                is not None
            ):
                node.exit_node.accept(
                    self
                )

        finally:
            self.scopes.pop()

    def visit_decl(
        self,
        node,
    ):
        current_scope = (
            self.scopes[-1]
        )

        # Duplicate only in current scope.
        # Shadowing outer variables
        # is allowed.
        if (
            node.name
            in current_scope
        ):
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"variable "
                f"'{node.name}' "
                "is already declared "
                "in this block"
            )

        # Check initializer before
        # making this declaration visible.
        node.init.accept(self)

        # Practice 4 feedback:
        # point at the constant itself.
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

        current_scope[
            node.name
        ] = node

    def visit_assign(
        self,
        node,
    ):
        decl = self.lookup(
            node,
            node.name,
        )

        if not decl.mutable:
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"cannot assign to "
                f"'{node.name}': "
                "it is not mut"
            )

        node.decl = decl

        node.value.accept(self)

        # Practice 4 feedback:
        #
        # i32 mut x{1}
        # x := 2147483648
        #
        # error must point at 2:6,
        # the constant.
        if (
            isinstance(
                node.value,
                ConstNode,
            )
            and decl.type_name
            == "i32"
            and node.value.type
            == "i64"
        ):
            raise CompileError(
                f"line "
                f"{node.value.line}:"
                f"{node.value.col}: "
                f"constant "
                f"{node.value.value} "
                "does not fit in i32"
            )

        self.check_assignable(
            node.value,
            decl.type_name,
            node,
            f"assign to "
            f"'{node.name}'",
        )

    def visit_if(
        self,
        node,
    ):
        condition_type = (
            node.condition.accept(
                self
            )
        )

        if condition_type != "bool":
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                "the condition of 'if' "
                "must be bool, "
                f"got {condition_type}"
            )

        node.then_block.accept(
            self
        )

        if (
            node.else_block
            is not None
        ):
            node.else_block.accept(
                self
            )

    def visit_while(
        self,
        node,
    ):
        condition_type = (
            node.condition.accept(
                self
            )
        )

        if condition_type != "bool":
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                "the condition of "
                "'while' must be bool, "
                f"got {condition_type}"
            )

        node.body.accept(self)

    def visit_exit(
        self,
        node,
    ):
        node.value.accept(self)

    # --------------------------------------------------------
    # Expressions
    # --------------------------------------------------------

    def visit_not(
        self,
        node,
    ):
        operand_type = (
            node.operand.accept(
                self
            )
        )

        if operand_type != "bool":
            raise CompileError(
                f"line {node.line}:"
                f"{node.col}: "
                f"cannot apply '!' "
                f"to {operand_type}"
            )

        node.type = "bool"

        return node.type

    def visit_const(
        self,
        node,
    ):
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

    def visit_bool(
        self,
        node,
    ):
        node.type = "bool"
        return node.type

    def visit_var(
        self,
        node,
    ):
        decl = self.lookup(
            node,
            node.name,
        )

        node.decl = decl

        node.type = (
            decl.type_name
        )

        return node.type

    def visit_binop(
        self,
        node,
    ):
        left_type = (
            node.left.accept(
                self
            )
        )

        right_type = (
            node.right.accept(
                self
            )
        )

        # ----------------------------------------------------
        # Arithmetic
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Equality
        # ----------------------------------------------------

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
                f"with {right_type}"
            )

        raise CompileError(
            f"line {node.line}:"
            f"{node.col}: "
            f"invalid operator "
            f"'{node.op}'"
        )

    # --------------------------------------------------------
    # Assignment conversion
    # --------------------------------------------------------

    def check_assignable(
        self,
        expr,
        want,
        at,
        what,
    ):
        have = expr.type

        if have == want:
            return

        # Only implicit conversion.
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


def llvm_type(
    type_name,
):
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
            name="practice5"
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

        self.main = (
            ir.Function(
                self.module,
                main_type,
                name="main",
            )
        )

        self.entry = (
            self.main
            .append_basic_block(
                "entry"
            )
        )

        self.builder = (
            ir.IRBuilder(
                self.entry
            )
        )

        # ----------------------------------------------------
        # printf
        # ----------------------------------------------------

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

    # --------------------------------------------------------
    # Strings
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Every alloca belongs to ENTRY.
    # --------------------------------------------------------

    def create_alloca(
        self,
        type_name,
        name,
    ):
        current_block = self.builder.block

        alloca_builder = ir.IRBuilder(
            self.entry
        )

        alloca_builder.position_at_start(
            self.entry
        )

        ptr = alloca_builder.alloca(
            llvm_type(type_name),
            name=name,
        )

        self.builder.position_at_end(
            current_block
        )

        return ptr
    # --------------------------------------------------------
    # Generate
    # --------------------------------------------------------

    def generate(
        self,
        program,
    ):
        program.accept(self)

        return str(
            self.module
        )

    # --------------------------------------------------------
    # Program / Block
    # --------------------------------------------------------

    def visit_program(
        self,
        node,
    ):
        for stmt in node.statements:
            if (
                self.builder.block
                .is_terminated
            ):
                break

            stmt.accept(self)

        if not (
            self.builder.block
            .is_terminated
        ):
            node.exit_node.accept(
                self
            )

    def visit_block(
        self,
        node,
    ):
        for stmt in node.statements:
            if (
                self.builder.block
                .is_terminated
            ):
                return

            stmt.accept(self)

        if (
            node.exit_node
            is not None
            and not (
                self.builder.block
                .is_terminated
            )
        ):
            node.exit_node.accept(
                self
            )

    # --------------------------------------------------------
    # Declaration / assignment
    # --------------------------------------------------------

    def visit_decl(
        self,
        node,
    ):
        ptr = self.create_alloca(
            node.type_name,
            node.name,
        )

        value = node.init.accept(
            self
        )

        value = self.coerce(
            value,
            node.init.type,
            node.type_name,
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
        value = node.value.accept(
            self
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

    # --------------------------------------------------------
    # IF
    # --------------------------------------------------------

    def visit_if(
        self,
        node,
    ):
        cond = (
            node.condition.accept(
                self
            )
        )

        then_bb = (
            self.main
            .append_basic_block(
                "then"
            )
        )

        else_bb = None

        if (
            node.else_block
            is not None
        ):
            else_bb = (
                self.main
                .append_basic_block(
                    "else"
                )
            )

        merge_bb = (
            self.main
            .append_basic_block(
                "merge"
            )
        )

        # Ends the current block.
        self.builder.cbranch(
            cond,
            then_bb,
            else_bb
            or merge_bb,
        )

        # ---------------- THEN ----------------

        self.builder.position_at_end(
            then_bb
        )

        node.then_block.accept(
            self
        )

        # Important:
        # check the CURRENT builder block,
        # because a nested if may have
        # moved the builder.
        if not (
            self.builder.block
            .is_terminated
        ):
            self.builder.branch(
                merge_bb
            )

        # ---------------- ELSE ----------------

        if else_bb is not None:
            self.builder.position_at_end(
                else_bb
            )

            node.else_block.accept(
                self
            )

            if not (
                self.builder.block
                .is_terminated
            ):
                self.builder.branch(
                    merge_bb
                )

        # ---------------- MERGE ----------------

        self.builder.position_at_end(
            merge_bb
        )

    # --------------------------------------------------------
    # WHILE - bonus
    # --------------------------------------------------------

    def visit_while(
        self,
        node,
    ):
        cond_bb = (
            self.main
            .append_basic_block(
                "while.cond"
            )
        )

        body_bb = (
            self.main
            .append_basic_block(
                "while.body"
            )
        )

        end_bb = (
            self.main
            .append_basic_block(
                "while.end"
            )
        )

        # entry/current -> condition
        self.builder.branch(
            cond_bb
        )

        # ---------------- CONDITION ----------------

        self.builder.position_at_end(
            cond_bb
        )

        cond = (
            node.condition.accept(
                self
            )
        )

        self.builder.cbranch(
            cond,
            body_bb,
            end_bb,
        )

        # ---------------- BODY ----------------

        self.builder.position_at_end(
            body_bb
        )

        node.body.accept(
            self
        )

        # Back edge.
        if not (
            self.builder.block
            .is_terminated
        ):
            self.builder.branch(
                cond_bb
            )

        # ---------------- END ----------------

        self.builder.position_at_end(
            end_bb
        )

    # --------------------------------------------------------
    # Exit
    # --------------------------------------------------------

    def visit_exit(
        self,
        node,
    ):
        value = (
            node.value.accept(
                self
            )
        )

        if (
            node.value.type
            in INT_TYPES
        ):
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
                [
                    text_ptr
                ],
            )

        else:
            raise RuntimeError(
                f"unknown exit type: "
                f"{node.value.type}"
            )

        # Exit terminates whichever
        # basic block it appears in.
        self.builder.ret(
            ir.Constant(
                I32,
                0,
            )
        )

    # --------------------------------------------------------
    # Expressions
    # --------------------------------------------------------

    def visit_not(
        self,
        node,
    ):
        value = (
            node.operand.accept(
                self
            )
        )

        # NOT i1 = xor with 1.
        return (
            self.builder.xor(
                value,
                ir.Constant(
                    I1,
                    1,
                ),
                name="not",
            )
        )

    def visit_const(
        self,
        node,
    ):
        return (
            ir.Constant(
                llvm_type(
                    node.type
                ),
                node.value,
            )
        )

    def visit_bool(
        self,
        node,
    ):
        return (
            ir.Constant(
                I1,
                (
                    1
                    if node.value
                    else 0
                ),
            )
        )

    def visit_var(
        self,
        node,
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

    def visit_binop(
        self,
        node,
    ):
        left = (
            node.left.accept(
                self
            )
        )

        right = (
            node.right.accept(
                self
            )
        )

        # ----------------------------------------------------
        # Arithmetic
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # == / !=
        # ----------------------------------------------------

        if node.op in (
            "==",
            "!=",
        ):
            # Integer operands need
            # the same width.
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
            f"unknown operator "
            f"'{node.op}'"
        )

    # --------------------------------------------------------
    # i32 -> i64
    # --------------------------------------------------------

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

        raise RuntimeError(
            "semantic checker "
            "allowed invalid "
            f"conversion "
            f"{have} -> {want}"
        )


# ============================================================
# COMPILER INTERFACE
# ============================================================


def parse_source(
    data,
):
    token_lines = lex(
        data
    )

    parser = Parser(
        token_lines
    )

    # Parsing only.
    #
    # IMPORTANT:
    # --ast must work even when
    # semantic checking would fail.
    return (
        parser.parse_program()
    )


def check_program(
    program,
):
    checker = (
        SemanticChecker()
    )

    checker.check(
        program
    )


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


def print_tokens(
    data,
):
    token_lines = lex(
        data
    )

    for tokens in token_lines:
        for token in tokens:
            print(
                f"{token.text!r} "
                f"{token.kind} "
                f"{token.line}:"
                f"{token.column}"
            )


# ============================================================
# CLI
# ============================================================


def main():
    # --------------------------------------------------------
    # --tokens
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # --ast
    # --------------------------------------------------------

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

            # Parse only.
            # No SemanticChecker here.
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

    # --------------------------------------------------------
    # Normal compilation
    # --------------------------------------------------------

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

        # 1. Parse.
        program = (
            parse_source(
                data
            )
        )

        # 2. Semantic pass.
        check_program(
            program
        )

        # 3. CodeGen only after
        # semantic checking succeeds.
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
