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
    "struct",
    "fn",
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
            if b == ord('"'):
                start_col = col
                j = data.find(b'"', i + 1)
                endline = data.find(b'\n', i + 1)
                if j < 0 or (endline >= 0 and endline < j):
                    raise CompileError(f"line {line}:{col}: unclosed string literal")
                raw = data[i + 1:j]
                tokens.append(Token("string", raw.decode("latin-1"), line, start_col))
                col += j - i + 1
                i = j + 1
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
            if b in (ord("+"), ord("*")):
                tokens.append(Token("operator", chr(b), line, col))
                i += 1
                col += 1
                continue
            if b == ord("-"):
                if i + 1 < len(data) and data[i + 1] == ord(">"):
                    tokens.append(Token("arrow", "->", line, col))
                    i += 2
                    col += 2
                else:
                    tokens.append(Token("operator", "-", line, col))
                    i += 1
                    col += 1
                continue
            if b == ord("("):
                tokens.append(Token("lparen", "(", line, col))
                i += 1
                col += 1
                continue
            if b == ord(")"):
                tokens.append(Token("rparen", ")", line, col))
                i += 1
                col += 1
                continue
            if b == ord(","):
                tokens.append(
                    Token(
                        "comma",
                        ",",
                        line,
                        col,
                    )
                )
                i += 1
                col += 1
                continue
            if b == ord("."):
                tokens.append(Token("dot", ".", line, col))
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
class FieldDeclNode(Node):
    def __init__(
        self,
        line,
        col,
        name,
        type_name,
        mutable,
    ):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        # SemanticChecker fills this.
        self.index = None
    def dump(self, indent=0):
        kind = "mut" if self.mutable else "const"
        return [
            " " * indent
            + f"Field {self.name} "
            + f"{self.type_name} "
            + kind
        ]
class StructDeclNode(Node):
    def __init__(
        self,
        line,
        col,
        name,
        fields,
    ):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.field_map = {}
        self.llvm_type = None
    def dump(self, indent=0):
        lines = [
            " " * indent + f"Struct {self.name}"
        ]
        for field in self.fields:
            lines.extend(field.dump(indent + 2))
        return lines
class ParamNode(Node):
    def __init__(self, line, col, name, type_name):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = False
        self.ptr = None
    def dump(self, indent=0):
        return [" " * indent + f"Param {self.name} {self.type_name}"]
class FunctionDeclNode(Node):
    def __init__(self, line, col, name, params, result_type, body):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.result_type = result_type
        self.body = body
        self.llvm_function = None
    def dump(self, indent=0):
        lines = [" " * indent + f"Function {self.name} -> {self.result_type}"]
        for param in self.params:
            lines.extend(param.dump(indent + 2))
        lines.extend(self.body.dump(indent + 2))
        return lines
class ProgramNode(Node):
    def __init__(
        self,
        structs,
        functions,
        statements,
        exit_node,
    ):
        super().__init__(1, 1)
        self.structs = structs
        self.functions = functions
        self.statements = statements
        self.exit_node = exit_node
    def dump(self, indent=0):
        lines = [
            " " * indent + "Program"
        ]
        for struct in self.structs:
            lines.extend(struct.dump(indent + 2))
        for function in self.functions:
            lines.extend(function.dump(indent + 2))
        for stmt in self.statements:
            lines.extend(stmt.dump(indent + 2))
        lines.extend(
            self.exit_node.dump(indent + 2)
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
        initializers,
    ):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.initializers = initializers
        # CodeGen fills this.
        self.ptr = None
    def dump(self, indent=0):
        kind = "mut" if self.mutable else "const"
        lines = [
            " " * indent
            + f"Decl {self.name} "
            + f"{self.type_name} "
            + kind
        ]
        for init in self.initializers:
            lines.extend(init.dump(indent + 2))
        return lines
class AssignNode(StmtNode):
    def __init__(self, line, col, name, fields, value):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.value = value
        self.decl = None
        self.resolved_fields = []
        self.target_type = None
    def dump(self, indent=0):
        target = self.name
        if self.fields:
            target += "." + ".".join(self.fields)
        lines = [" " * indent + f"Assign {target}"]
        lines.extend(self.value.dump(indent + 2))
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
class FieldAccessNode(ExprNode):
    def __init__(self, line, col, name, fields):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.decl = None
        self.resolved_fields = []
    def dump(self, indent=0):
        return [" " * indent + f"Field {self.name}." + ".".join(self.fields)]
class CallNode(ExprNode):
    def __init__(self, line, col, name, args):
        super().__init__(line, col)
        self.name = name
        self.args = args
        self.function = None
    def dump(self, indent=0):
        lines = [" " * indent + f"Call {self.name}"]
        for arg in self.args:
            lines.extend(arg.dump(indent + 2))
        return lines
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
        structs = []
        functions = []
        statements = []
        exit_node = None
        phase = "structs"
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
                token_error(first, "'}' without an open block")
            if first.text == "else":
                token_error(first, "'else' without an 'if'")
            if exit_node is not None:
                token_error(first, "code after exit")
            if first.text == "struct":
                if phase != "structs":
                    token_error(first, "struct declaration must appear before functions and statements")
                structs.append(self.parse_struct())
                continue
            if first.text == "fn":
                if phase == "statements":
                    token_error(first, "function declaration must appear before statements")
                phase = "functions"
                functions.append(self.parse_function())
                continue
            if first.text == "exit":
                phase = "statements"
                exit_node = self.parse_exit()
                self.line_finished()
                continue
            phase = "statements"
            statements.append(self.parse_statement())
            self.line_finished()
        if exit_node is None:
            raise CompileError(f"line {last_line}:{last_end_col}: program has no exit statement")
        return ProgramNode(structs, functions, statements, exit_node)
    # --------------------------------------------------------
    # Struct declarations
    # --------------------------------------------------------
    def parse_struct(self):
        struct_tok = self.expect_text("struct")
        name_tok = self.expect_kind(
            "identifier",
            "a struct name",
        )
        self.line_finished()
        tokens = self.next_line()
        if tokens is None:
            raise CompileError(
                f"line {struct_tok.line}:"
                f"{struct_tok.column}: "
                f"struct '{name_tok.text}' has no body"
            )
        open_tok = self.expect_text(
            "{",
            "expected '{' on its own line after struct declaration",
        )
        self.line_finished()
        fields = []
        while True:
            tokens = self.next_line()
            if tokens is None:
                raise CompileError(
                    f"line {open_tok.line}:"
                    f"{open_tok.column}: "
                    "'{' is never closed"
                )
            first = self.peek()
            if first.text == "}":
                close_tok = self.eat()
                self.line_finished()
                if not fields:
                    token_error(
                        close_tok,
                        "struct must have at least one field",
                    )
                break
            type_tok = self.eat()
            if not (
                type_tok.text in ("i32", "i64", "bool")
                or type_tok.kind == "identifier"
            ):
                token_error(type_tok, "expected a field type")
            mutable = False
            if (
                self.peek() is not None
                and self.peek().text == "mut"
            ):
                self.eat()
                mutable = True
            name = self.expect_kind(
                "identifier",
                "a field name",
            )
            self.line_finished()
            fields.append(
                FieldDeclNode(
                    name.line,
                    name.column,
                    name.text,
                    type_tok.text,
                    mutable,
                )
            )
        return StructDeclNode(
            struct_tok.line,
            struct_tok.column,
            name_tok.text,
            fields,
        )
    # --------------------------------------------------------
    # Function declarations
    # --------------------------------------------------------
    def parse_function(self):
        fn_tok = self.expect_text("fn")
        name_tok = self.expect_kind("identifier", "a function name")
        self.expect_text(":=", "expected ':=' after function name")
        self.expect_text("(", "expected '(' after ':='")
        params = []
        if self.peek() is not None and self.peek().text != ")":
            while True:
                type_tok = self.eat()
                if not (type_tok.text in ("i32", "i64", "bool") or type_tok.kind == "identifier"):
                    token_error(type_tok, "expected a parameter type")
                param_tok = self.expect_kind("identifier", "a parameter name")
                params.append(ParamNode(param_tok.line, param_tok.column, param_tok.text, type_tok.text))
                if self.peek() is None or self.peek().text != ",":
                    break
                self.eat()
        self.expect_text(")", "expected ')' after parameters")
        self.expect_text("->", "expected '->' after parameters")
        result_tok = self.eat()
        if not (result_tok.text in ("i32", "i64", "bool") or result_tok.kind == "identifier"):
            token_error(result_tok, "expected a function result type")
        self.line_finished()
        body = self.parse_block(f"function {name_tok.text}", fn_tok)
        if body.exit_node is None:
            raise CompileError(f"line {body.line}:{body.col}: function '{name_tok.text}' must end with exit")
        return FunctionDeclNode(fn_tok.line, fn_tok.column, name_tok.text, params, result_tok.text, body)
    # --------------------------------------------------------
    # Statements
    # --------------------------------------------------------
    def parse_statement(self):
        tok = self.peek()
        if tok is None:
            self.error_at_end("expected a statement")
        if tok.text in ("i32", "i64", "bool"):
            return self.parse_decl()
        if tok.text == "if":
            return self.parse_if()
        if tok.text == "while":
            return self.parse_while()
        if tok.kind == "identifier":
            next_pos = self.pos + 1
            if next_pos < len(self.toks):
                next_tok = self.toks[next_pos]
                if (
                    next_tok.kind == "identifier"
                    or next_tok.text == "mut"
                ):
                    return self.parse_decl()
            return self.parse_assign()
        token_error(
            tok,
            f"cannot start a statement with '{tok.text}'",
        )
    def parse_decl(self):
        type_tok = self.eat()
        mutable = False
        if (
            self.peek() is not None
            and self.peek().text == "mut"
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
                f"variable '{name.text}' needs an initialiser in {{}}",
            )
        if self.peek().text != "{":
            token_error(
                self.peek(),
                f"variable '{name.text}' needs an initialiser in {{}}",
            )
        self.eat()
        if self.peek() is None:
            self.error_at_end("expected an initialiser")
        initializers = [self.parse_expr()]
        while (
            self.peek() is not None
            and self.peek().text == ","
        ):
            self.eat()
            if self.peek() is None:
                self.error_at_end(
                    "expected an expression after ','"
                )
            initializers.append(self.parse_expr())
        self.expect_text(
            "}",
            "expected '}' after initialiser",
        )
        return DeclNode(
            name.line,
            name.column,
            name.text,
            type_tok.text,
            mutable,
            initializers,
        )
    def parse_assign(self):
        name = self.expect_kind("identifier", "a variable name")
        fields = []
        while self.peek() is not None and self.peek().text == ".":
            self.eat()
            field = self.expect_kind("identifier", "a field name")
            fields.append(field.text)
        target = name.text + ("." + ".".join(fields) if fields else "")
        self.expect_text(":=", f"expected ':=' after '{target}'")
        if self.peek() is None:
            self.error_at_end("expected a constant or a variable")
        value = self.parse_expr()
        return AssignNode(name.line, name.column, name.text, fields, value)
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
            if self.peek() is not None and self.peek().text == "(":
                self.eat()
                args = []
                if self.peek() is not None and self.peek().text != ")":
                    args.append(self.parse_expr())
                    while self.peek() is not None and self.peek().text == ",":
                        self.eat()
                        args.append(self.parse_expr())
                self.expect_text(")", "expected ')' after function arguments")
                return CallNode(tok.line, tok.column, tok.text, args)
            fields = []
            while self.peek() is not None and self.peek().text == ".":
                self.eat()
                field = self.expect_kind("identifier", "a field name")
                fields.append(field.text)
            if fields:
                return FieldAccessNode(tok.line, tok.column, tok.text, fields)
            return VarNode(tok.line, tok.column, tok.text)
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
        # Struct declarations visible so far.
        self.structs = {}
        self.functions = {}
        self.current_function = None
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
    def visit_program(self, node):
        for struct in node.structs:
            struct.accept(self)
        # Collect every function signature before checking any body.
        for function in node.functions:
            if function.name in self.functions:
                raise CompileError(f"line {function.line}:{function.col}: function '{function.name}' is already declared")
            if not self.is_known_type(function.result_type):
                raise CompileError(f"line {function.line}:{function.col}: unknown result type '{function.result_type}'")
            seen = set()
            for param in function.params:
                if not self.is_known_type(param.type_name):
                    raise CompileError(f"line {param.line}:{param.col}: unknown parameter type '{param.type_name}'")
                if param.name in seen:
                    raise CompileError(f"line {param.line}:{param.col}: parameter '{param.name}' is already declared")
                seen.add(param.name)
            self.functions[function.name] = function
        for function in node.functions:
            function.accept(self)
        for stmt in node.statements:
            stmt.accept(self)
        node.exit_node.accept(self)
    def visit_structdecl(
        self,
        node,
    ):
        if node.name in self.structs:
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"struct '{node.name}' is already declared"
            )
        field_map = {}
        for index, field in enumerate(node.fields):
            if field.name in field_map:
                raise CompileError(
                    f"line {field.line}:{field.col}: "
                    f"field '{field.name}' is already declared "
                    f"in struct '{node.name}'"
                )
            if (
                field.type_name not in ("i32", "i64", "bool")
                and field.type_name not in self.structs
            ):
                raise CompileError(
                    f"line {field.line}:{field.col}: "
                    f"unknown field type '{field.type_name}'; "
                    "a struct field may use only a built-in type "
                    "or a struct declared above"
                )
            field.index = index
            field_map[field.name] = field
        node.field_map = field_map
        self.structs[node.name] = node
    def visit_functiondecl(self, node):
        saved_scopes = self.scopes
        saved_function = self.current_function
        self.scopes = [{}]
        self.current_function = node
        try:
            for param in node.params:
                self.scopes[0][param.name] = param
            node.body.accept(self)
        finally:
            self.scopes = saved_scopes
            self.current_function = saved_function
    def visit_block(
        self,
        node,
    ):
        self.scopes.append({})
        try:
            for stmt in node.statements:
                stmt.accept(self)
            if node.exit_node is not None:
                node.exit_node.accept(self)
        finally:
            self.scopes.pop()
    def is_known_type(self, type_name):
        return (
            type_name in ("i32", "i64", "bool")
            or type_name in self.structs
        )
    def struct_all_fields_mut(self, type_name):
        struct = self.structs[type_name]
        for field in struct.fields:
            if not field.mutable:
                return False
            if (
                field.type_name in self.structs
                and not self.struct_all_fields_mut(field.type_name)
            ):
                return False
        return True
    def visit_decl(
        self,
        node,
    ):
        current_scope = self.scopes[-1]
        if node.name in current_scope:
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"variable '{node.name}' is already declared "
                "in this block"
            )
        if not self.is_known_type(node.type_name):
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"unknown type '{node.type_name}'"
            )
        for init in node.initializers:
            init.accept(self)
        if node.type_name in ("i32", "i64", "bool"):
            if len(node.initializers) != 1:
                raise CompileError(
                    f"line {node.line}:{node.col}: "
                    f"type {node.type_name} needs exactly one "
                    "initialiser value"
                )
            init = node.initializers[0]
            if (
                isinstance(init, ConstNode)
                and node.type_name == "i32"
                and init.type == "i64"
            ):
                raise CompileError(
                    f"line {init.line}:{init.col}: "
                    f"constant {init.value} does not fit in i32"
                )
            self.check_assignable(
                init,
                node.type_name,
                node,
                f"initialise '{node.name}'",
            )
        else:
            struct = self.structs[node.type_name]
            if (
                len(node.initializers) == 1
                and node.initializers[0].type == node.type_name
            ):
                pass
            else:
                if len(node.initializers) != len(struct.fields):
                    raise CompileError(
                        f"line {node.line}:{node.col}: "
                        f"struct '{node.type_name}' needs "
                        f"{len(struct.fields)} value(s), got "
                        f"{len(node.initializers)}"
                    )
                for init, field in zip(
                    node.initializers,
                    struct.fields,
                ):
                    self.check_assignable(
                        init,
                        field.type_name,
                        init,
                        f"initialise field '{field.name}'",
                    )
        current_scope[node.name] = node
    def resolve_field_chain(self, node, base_decl, field_names):
        current_type = base_decl.type_name
        resolved = []
        for name in field_names:
            if current_type not in self.structs:
                raise CompileError(
                    f"line {node.line}:{node.col}: "
                    f"type '{current_type}' has no fields"
                )
            struct = self.structs[current_type]
            if name not in struct.field_map:
                raise CompileError(
                    f"line {node.line}:{node.col}: "
                    f"unknown field '{name}' in struct '{current_type}'"
                )
            field = struct.field_map[name]
            resolved.append(field)
            current_type = field.type_name
        return resolved, current_type
    def visit_assign(self, node):
        decl = self.lookup(node, node.name)
        node.decl = decl
        if not decl.mutable:
            if node.fields:
                message = (
                    f"cannot assign through "
                    f"'{node.name}': it is not mut"
                )
            else:
                message = (
                    f"cannot assign to "
                    f"'{node.name}': it is not mut"
                )
            raise CompileError(
                f"line {node.line}:{node.col}: "
                f"{message}"
            )
        node.value.accept(self)
        if not node.fields:
            node.target_type = decl.type_name
            if (
                isinstance(node.value, ConstNode)
                and decl.type_name == "i32"
                and node.value.type == "i64"
            ):
                raise CompileError(
                    f"line {node.value.line}:{node.value.col}: "
                    f"constant {node.value.value} does not fit in i32"
                )
            if (
                decl.type_name in self.structs
                and not self.struct_all_fields_mut(decl.type_name)
            ):
                raise CompileError(
                    f"line {node.line}:{node.col}: "
                    f"cannot replace struct '{node.name}': "
                    "not all fields are mut at every depth"
                )
        else:
            resolved, target_type = self.resolve_field_chain(node, decl, node.fields)
            node.resolved_fields = resolved
            node.target_type = target_type
            for field in resolved:
                if not field.mutable:
                    raise CompileError(
                        f"line {node.line}:{node.col}: "
                        f"cannot assign through field '{field.name}': it is not mut"
                    )
            if (
                isinstance(node.value, ConstNode)
                and target_type == "i32"
                and node.value.type == "i64"
            ):
                raise CompileError(
                    f"line {node.value.line}:{node.value.col}: "
                    f"constant {node.value.value} does not fit in i32"
                )
        self.check_assignable(
            node.value,
            node.target_type,
            node,
            f"assign to '{node.name + ('.' + '.'.join(node.fields) if node.fields else '')}'",
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
    def visit_exit(self, node):
        result_type = node.value.accept(self)
        if self.current_function is None:
            if result_type not in ("i32", "i64", "bool"):
                raise CompileError(f"line {node.line}:{node.col}: top-level exit must have a built-in type")
            return
        want = self.current_function.result_type
        self.check_assignable(node.value, want, node, f"return from function '{self.current_function.name}'")
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
    def visit_fieldaccess(self, node):
        decl = self.lookup(node, node.name)
        node.decl = decl
        resolved, result_type = self.resolve_field_chain(node, decl, node.fields)
        node.resolved_fields = resolved
        node.type = result_type
        return node.type
    def visit_call(self, node):
        if node.name not in self.functions:
            raise CompileError(f"line {node.line}:{node.col}: unknown function '{node.name}'")
        function = self.functions[node.name]
        node.function = function
        if len(node.args) != len(function.params):
            raise CompileError(f"line {node.line}:{node.col}: function '{node.name}' expects {len(function.params)} argument(s), got {len(node.args)}")
        for arg, param in zip(node.args, function.params):
            arg.accept(self)
            self.check_assignable(arg, param.type_name, arg, f"pass argument to parameter '{param.name}'")
        node.type = function.result_type
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
    struct_types=None,
):
    if type_name == "i32":
        return I32
    if type_name == "i64":
        return I64
    if type_name == "bool":
        return I1
    if (
        struct_types is not None
        and type_name in struct_types
    ):
        return struct_types[type_name]
    raise RuntimeError(f"unknown type: {type_name}")
class CodeGen:
    def __init__(self):
        self.module = ir.Module(
            name="practice6"
        )
        self.struct_types = {}
        self.functions = {}
        self.current_function_decl = None
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
        self.current_ir_function = self.main
        self.entry = (
            self.current_ir_function
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
            llvm_type(type_name, self.struct_types),
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
        self.struct_decls = {
            struct.name: struct
            for struct in program.structs
        }
        program.accept(self)
        return str(
            self.module
        )
    # --------------------------------------------------------
    # Program / Block
    # --------------------------------------------------------
    def visit_program(self, node):
        # Struct types must exist before function signatures use them.
        for struct in node.structs:
            llvm_struct = self.module.context.get_identified_type(struct.name)
            self.struct_types[struct.name] = llvm_struct
            struct.llvm_type = llvm_struct
        for struct in node.structs:
            struct.llvm_type.set_body(*[llvm_type(field.type_name, self.struct_types) for field in struct.fields])
        # Declare every function first, so recursion and forward calls work.
        for function in node.functions:
            fn_type = ir.FunctionType(
                llvm_type(function.result_type, self.struct_types),
                [llvm_type(param.type_name, self.struct_types) for param in function.params],
            )
            llvm_fn = ir.Function(self.module, fn_type, name=f"user_fn_{function.name}")
            function.llvm_function = llvm_fn
            self.functions[function.name] = llvm_fn
        # Generate function bodies.
        for function in node.functions:
            function.accept(self)
        # Restore main context and generate top-level statements.
        self.current_function_decl = None
        self.current_ir_function = self.main
        self.entry = self.main.entry_basic_block
        self.builder = ir.IRBuilder(self.entry)
        self.builder.position_at_end(self.entry)
        for stmt in node.statements:
            if self.builder.block.is_terminated:
                break
            stmt.accept(self)
        if not self.builder.block.is_terminated:
            node.exit_node.accept(self)
    def visit_functiondecl(self, node):
        saved_builder = self.builder
        saved_entry = self.entry
        saved_ir_function = self.current_ir_function
        saved_decl = self.current_function_decl
        llvm_fn = node.llvm_function
        entry = llvm_fn.append_basic_block("entry")
        self.current_ir_function = llvm_fn
        self.current_function_decl = node
        self.entry = entry
        self.builder = ir.IRBuilder(entry)
        for arg, param in zip(llvm_fn.args, node.params):
            arg.name = param.name
            ptr = self.create_alloca(param.type_name, param.name)
            self.builder.store(arg, ptr)
            param.ptr = ptr
        node.body.accept(self)
        self.builder = saved_builder
        self.entry = saved_entry
        self.current_ir_function = saved_ir_function
        self.current_function_decl = saved_decl
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
        if node.type_name not in self.struct_types:
            init = node.initializers[0]
            value = init.accept(self)
            value = self.coerce(
                value,
                init.type,
                node.type_name,
            )
            self.builder.store(value, ptr)
            node.ptr = ptr
            return
        struct_decl = None
        # Semantic pass attached only the type name to the declaration;
        # locate field information through the program-independent map
        # saved below by generate().
        struct_decl = self.struct_decls[node.type_name]
        if (
            len(node.initializers) == 1
            and node.initializers[0].type == node.type_name
        ):
            value = node.initializers[0].accept(self)
            self.builder.store(value, ptr)
            node.ptr = ptr
            return
        zero = ir.Constant(I32, 0)
        for index, (init, field) in enumerate(
            zip(node.initializers, struct_decl.fields)
        ):
            field_ptr = self.builder.gep(
                ptr,
                [zero, ir.Constant(I32, index)],
                inbounds=True,
                name=f"{node.name}_{field.name}_ptr",
            )
            value = init.accept(self)
            value = self.coerce(
                value,
                init.type,
                field.type_name,
            )
            self.builder.store(value, field_ptr)
        node.ptr = ptr
    def field_pointer(self, decl, resolved_fields, name):
        ptr = decl.ptr
        zero = ir.Constant(I32, 0)
        for field in resolved_fields:
            ptr = self.builder.gep(
                ptr,
                [zero, ir.Constant(I32, field.index)],
                inbounds=True,
                name=f"{name}_{field.name}_ptr",
            )
        return ptr
    def visit_assign(self, node):
        value = node.value.accept(self)
        value = self.coerce(value, node.value.type, node.target_type)
        ptr = node.decl.ptr
        if node.resolved_fields:
            ptr = self.field_pointer(node.decl, node.resolved_fields, node.name)
        self.builder.store(value, ptr)
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
            self.current_ir_function
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
                self.current_ir_function
                .append_basic_block(
                    "else"
                )
            )
        merge_bb = (
            self.current_ir_function
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
            self.current_ir_function
            .append_basic_block(
                "while.cond"
            )
        )
        body_bb = (
            self.current_ir_function
            .append_basic_block(
                "while.body"
            )
        )
        end_bb = (
            self.current_ir_function
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
    def visit_exit(self, node):
        value = node.value.accept(self)
        if self.current_function_decl is not None:
            value = self.coerce(value, node.value.type, self.current_function_decl.result_type)
            self.builder.ret(value)
            return
        if node.value.type in INT_TYPES:
            value = self.coerce(value, node.value.type, "i64")
            self.builder.call(self.printf, [self.string_ptr(self.int_fmt), value])
        elif node.value.type == "bool":
            true_ptr = self.string_ptr(self.bool_true)
            false_ptr = self.string_ptr(self.bool_false)
            text_ptr = self.builder.select(value, true_ptr, false_ptr, name="bool_text")
            self.builder.call(self.printf, [text_ptr])
        else:
            raise RuntimeError(f"unknown exit type: {node.value.type}")
        self.builder.ret(ir.Constant(I32, 0))
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
    def visit_fieldaccess(self, node):
        ptr = self.field_pointer(node.decl, node.resolved_fields, node.name)
        return self.builder.load(ptr, name=f"load_{node.name}_{'_'.join(node.fields)}")
    def visit_call(self, node):
        values = []
        for arg, param in zip(node.args, node.function.params):
            value = arg.accept(self)
            value = self.coerce(value, arg.type, param.type_name)
            values.append(value)
        return self.builder.call(node.function.llvm_function, values, name=f"call_{node.name}")
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
# ============================================================
# PRACTICE 7: MEMBER FUNCTIONS, I/O, AND RESULT CHAINS
# Extensions to the existing Practice 6 visitor architecture.
# ============================================================
_RESERVED_P7 = {"read", "print"}
def _p7_identifier(token):
    if token.text in _RESERVED_P7:
        token_error(token, f"'{token.text}' is reserved")
    return token
class MemberFnNode(FunctionDeclNode):
    def dump(self, indent=0):
        lines = [" " * indent + f"MemberFn {self.name} -> {self.result_type}"]
        for param in self.params:
            lines.extend(param.dump(indent + 2))
        lines.extend(self.body.dump(indent + 2))
        return lines
class MemberCallNode(ExprNode):
    def __init__(self, token, receiver, name, args):
        super().__init__(token.line, token.column)
        self.receiver = receiver
        self.name = name
        self.args = args
        self.function = None
        self.receiver_is_temporary = False
    def dump(self, indent=0):
        lines = [" " * indent + f"MemberCall {self.name}"]
        lines.extend(self.receiver.dump(indent + 2))
        for arg in self.args:
            lines.extend(arg.dump(indent + 2))
        return lines
class ResultFieldNode(ExprNode):
    def __init__(self, token, receiver, name):
        super().__init__(token.line, token.column)
        self.receiver = receiver
        self.name = name
        self.field = None
    def dump(self, indent=0):
        lines = [" " * indent + f"ResultField {self.name}"]
        lines.extend(self.receiver.dump(indent + 2))
        return lines
class StringNode(ExprNode):
    def __init__(self, token):
        super().__init__(token.line, token.column)
        self.value = token.text
    def dump(self, indent=0):
        return [" " * indent + f"String {self.value!r}"]
class PrintNode(StmtNode):
    def __init__(self, token, value):
        super().__init__(token.line, token.column)
        self.value = value
    def dump(self, indent=0):
        return [" " * indent + "Print"] + self.value.dump(indent + 2)
# Preserve the existing AST shape and every existing visitor. Only add
# methods to StructDeclNode so the old field-only structs work unchanged.
_old_struct_init = StructDeclNode.__init__
_old_struct_dump = StructDeclNode.dump
def _p7_struct_init(self, line, col, name, fields, member_functions=None):
    _old_struct_init(self, line, col, name, fields)
    self.member_functions = member_functions or []
    self.method_map = {}
def _p7_struct_dump(self, indent=0):
    lines = _old_struct_dump(self, indent)
    for method in self.member_functions:
        lines.extend(method.dump(indent + 2))
    return lines
StructDeclNode.__init__ = _p7_struct_init
StructDeclNode.dump = _p7_struct_dump
# The original lexer handles line/column locations; extend only the string
# branch in START (see the source edit just above this extension).
_old_parse_function = Parser.parse_function
_old_parse_decl = Parser.parse_decl
_old_parse_assign = Parser.parse_assign
def _p7_function(self, member=False):
    result = _old_parse_function(self)
    _p7_identifier(Token("identifier", result.name, result.line, result.col + 3))
    for p in result.params:
        _p7_identifier(Token("identifier", p.name, p.line, p.col))
    if member:
        result.__class__ = MemberFnNode
    return result
def _p7_struct(self):
    struct_tok = self.expect_text("struct")
    name_tok = _p7_identifier(self.expect_kind("identifier", "a struct name"))
    self.line_finished()
    self.next_line()
    opening = self.expect_text("{", "expected '{' after struct declaration")
    self.line_finished()
    fields, methods = [], []
    seen_method = False
    while True:
        if self.next_line() is None:
            token_error(opening, "'{' is never closed")
        t = self.peek()
        if t.text == "}":
            self.eat()
            self.line_finished()
            if not fields:
                token_error(t, "struct must have at least one field")
            return StructDeclNode(struct_tok.line, struct_tok.column, name_tok.text, fields, methods)
        if t.text == "fn":
            if not fields:
                token_error(t, "member function before first field")
            seen_method = True
            methods.append(self.parse_function(member=True))
            continue
        if seen_method:
            token_error(t, "field after member function")
        typ = self.eat()
        if typ.text not in ("i32", "i64", "bool") and typ.kind != "identifier":
            token_error(typ, "expected a field type")
        mutable = bool(self.peek() and self.peek().text == "mut" and self.eat())
        name = _p7_identifier(self.expect_kind("identifier", "a field name"))
        self.line_finished()
        fields.append(FieldDeclNode(name.line, name.column, name.text, typ.text, mutable))
def _p7_decl(self):
    node = _old_parse_decl(self)
    _p7_identifier(Token("identifier", node.name, node.line, node.col))
    return node
def _p7_statement(self):
    t = self.peek()
    if t.text == "print":
        tok = self.eat()
        self.expect_text("(")
        if self.peek() and self.peek().text == ")":
            token_error(self.peek(), "print needs one argument")
        expr = self.parse_expr()
        self.expect_text(")")
        return PrintNode(tok, expr)
    return _p7_original_parse_statement(self)
def _p7_arguments(self):
    self.expect_text("(")
    args = []
    if self.peek() and self.peek().text != ")":
        args.append(self.parse_expr())
        while self.peek() and self.peek().text == ",":
            self.eat()
            args.append(self.parse_expr())
    self.expect_text(")")
    return args
def _p7_factor(self):
    tok = self.peek()
    if tok is None:
        self.error_at_end("expected expression")
    if tok.text == "!":
        self.eat()
        return NotNode(tok.line, tok.column, self.parse_factor())
    if tok.kind == "string":
        self.eat()
        return StringNode(tok)
    if tok.kind == "number":
        self.eat()
        node = ConstNode(tok.line, tok.column, int(tok.text))
    elif tok.text in ("true", "false"):
        self.eat()
        node = BoolNode(tok.line, tok.column, tok.text == "true")
    elif tok.text == "(":
        self.eat()
        node = self.parse_expr()
        self.expect_text(")")
    elif tok.text in ("read", "print") or tok.kind == "identifier":
        self.eat()
        if self.peek() and self.peek().text == "(":
            args = _p7_arguments(self)
            node = CallNode(tok.line, tok.column, tok.text, args)
        else:
            if tok.text in _RESERVED_P7:
                token_error(tok, f"'{tok.text}' is reserved")
            node = VarNode(tok.line, tok.column, tok.text)
    else:
        token_error(tok, f"expected expression, got '{tok.text}'")
    while self.peek() and self.peek().text == ".":
        dot = self.eat()
        name = self.expect_kind("identifier", "a field or member function name")
        _p7_identifier(name)
        if self.peek() and self.peek().text == "(":
            node = MemberCallNode(name, node, name.text, _p7_arguments(self))
        elif isinstance(node, (VarNode, FieldAccessNode)):
            if isinstance(node, VarNode):
                node = FieldAccessNode(node.line, node.col, node.name, [name.text])
            else:
                node.fields.append(name.text)
        else:
            node = ResultFieldNode(name, node, name.text)
    return node
_p7_original_parse_statement = Parser.parse_statement
Parser.parse_function = _p7_function
Parser.parse_struct = _p7_struct
Parser.parse_decl = _p7_decl
Parser.parse_statement = _p7_statement
Parser.parse_factor = _p7_factor
# Semantic checker: names in member bodies prefer locals/parameters over
# fields, and calls are analysed for mutation after all functions are seen.
_old_semantic_program = SemanticChecker.visit_program
_old_lookup = SemanticChecker.lookup
_old_semantic_struct = SemanticChecker.visit_structdecl
_old_semantic_function = SemanticChecker.visit_functiondecl
_old_semantic_var = SemanticChecker.visit_var
_old_semantic_field = SemanticChecker.visit_fieldaccess
_old_semantic_call = SemanticChecker.visit_call
_old_semantic_assign = SemanticChecker.visit_assign
def _p7_lookup(self, node, name):
    for frame in reversed(self.scopes):
        if name in frame:
            return frame[name]
    if getattr(self, "current_struct", None) and name in self.current_struct.field_map:
        field = self.current_struct.field_map[name]
        return field
    return _old_lookup(self, node, name)
def _p7_struct_sem(self, node):
    _old_semantic_struct(self, node)
    node.method_map = {}
    for method in node.member_functions:
        if method.name in node.field_map or method.name in node.method_map:
            raise CompileError(f"line {method.line}:{method.col}: duplicate member '{method.name}'")
        node.method_map[method.name] = method
        method.owner = node
        method.direct_mutating = False
        method.mutating = False
        method.dependencies = set()
def _p7_program_sem(self, node):
    self.current_struct = None
    self.pending_member_calls = []
    for struct in node.structs:
        struct.accept(self)
    for fn in node.functions:
        if fn.name in self.functions:
            raise CompileError(f"line {fn.line}:{fn.col}: duplicate function '{fn.name}'")
        self.functions[fn.name] = fn
    for fn in node.functions + [m for s in node.structs for m in s.member_functions]:
        if not self.is_known_type(fn.result_type):
            raise CompileError(f"line {fn.line}:{fn.col}: unknown return type '{fn.result_type}'")
        seen = set()
        for p in fn.params:
            if not self.is_known_type(p.type_name):
                raise CompileError(f"line {p.line}:{p.col}: unknown parameter type '{p.type_name}'")
            if p.name in seen:
                raise CompileError(f"line {p.line}:{p.col}: duplicate parameter '{p.name}'")
            seen.add(p.name)
    for fn in node.functions:
        fn.accept(self)
    for struct in node.structs:
        for fn in struct.member_functions:
            fn.accept(self)
    changed = True
    while changed:
        changed = False
        for struct in node.structs:
            for fn in struct.member_functions:
                flag = fn.direct_mutating or any(dep.mutating for dep in fn.dependencies)
                if flag and not fn.mutating:
                    fn.mutating = True
                    changed = True
    self.current_function = None
    self.current_struct = None
    self.scopes = [{}]
    for stmt in node.statements:
        stmt.accept(self)
    node.exit_node.accept(self)
    for call, method, links, temporary in self.pending_member_calls:
        if method.mutating and not temporary and not all(links):
            raise CompileError(f"line {call.line}:{call.col}: mutating call through const link")
def _p7_function_sem(self, node):
    previous = getattr(self, "current_struct", None)
    self.current_struct = getattr(node, "owner", None)
    try:
        _old_semantic_function(self, node)
    finally:
        self.current_struct = previous
def _p7_var_sem(self, node):
    result = _old_semantic_var(self, node)
    node.implicit_field = isinstance(node.decl, FieldDeclNode)
    return result
def _p7_field_sem(self, node):
    result = _old_semantic_field(self, node)
    node.implicit_field = isinstance(node.decl, FieldDeclNode)
    return result
def _p7_path(self, expr):
    if isinstance(expr, VarNode):
        return [True if getattr(expr, "implicit_field", False) else expr.decl.mutable], False
    if isinstance(expr, FieldAccessNode):
        return [True if getattr(expr, "implicit_field", False) else expr.decl.mutable] + [f.mutable for f in expr.resolved_fields], False
    if isinstance(expr, ResultFieldNode):
        links, temp = _p7_path(self, expr.receiver)
        return links + [expr.field.mutable], temp
    return [], True
def _p7_self_root(self, expr):
    if isinstance(expr, (VarNode, FieldAccessNode)):
        return getattr(expr, "implicit_field", False)
    if isinstance(expr, ResultFieldNode):
        return _p7_self_root(self, expr.receiver)
    return False
def _p7_arguments_sem(self, node, fn, args):
    if len(args) != len(fn.params):
        raise CompileError(f"line {node.line}:{node.col}: '{fn.name}' expects {len(fn.params)} arguments, got {len(args)}")
    for arg, param in zip(args, fn.params):
        arg.accept(self)
        self.check_assignable(arg, param.type_name, arg, "pass argument")
def _p7_call_sem(self, node):
    if node.name == "read":
        if node.args:
            raise CompileError(f"line {node.line}:{node.col}: read() takes no arguments")
        node.type = "i32"
        node.function = "read"
        return node.type
    if node.name == "print":
        raise CompileError(f"line {node.line}:{node.col}: print is a statement, not a value")
    struct = getattr(self, "current_struct", None)
    if struct and node.name in struct.method_map:
        fn = struct.method_map[node.name]
        node.function = fn
        node.member_on_this = True
        _p7_arguments_sem(self, node, fn, node.args)
        if self.current_function and isinstance(self.current_function, MemberFnNode):
            self.current_function.dependencies.add(fn)
        self.pending_member_calls.append((node, fn, [True], False))
        node.type = fn.result_type
        return node.type
    return _old_semantic_call(self, node)
def _p7_membercall_sem(self, node):
    receiver_type = node.receiver.accept(self)
    if receiver_type not in self.structs:
        raise CompileError(f"line {node.line}:{node.col}: member call on non-struct '{receiver_type}'")
    struct = self.structs[receiver_type]
    if node.name not in struct.method_map:
        raise CompileError(f"line {node.line}:{node.col}: unknown member function '{node.name}'")
    fn = struct.method_map[node.name]
    node.function = fn
    _p7_arguments_sem(self, node, fn, node.args)
    links, temporary = _p7_path(self, node.receiver)
    node.receiver_is_temporary = temporary
    self.pending_member_calls.append((node, fn, links, temporary))
    if self.current_function and isinstance(self.current_function, MemberFnNode) and _p7_self_root(self, node.receiver):
        self.current_function.dependencies.add(fn)
    node.type = fn.result_type
    return node.type
def _p7_resultfield_sem(self, node):
    receiver_type = node.receiver.accept(self)
    if receiver_type not in self.structs:
        raise CompileError(f"line {node.line}:{node.col}: '.' after non-struct result")
    struct = self.structs[receiver_type]
    if node.name not in struct.field_map:
        raise CompileError(f"line {node.line}:{node.col}: unknown field '{node.name}'")
    node.field = struct.field_map[node.name]
    node.type = node.field.type_name
    return node.type
def _p7_string_sem(self, node):
    node.type = "string"
    return node.type
def _p7_print_sem(self, node):
    kind = node.value.accept(self)
    if kind not in {"i32", "i64", "bool", "string"} and kind not in self.structs:
        raise CompileError(f"line {node.line}:{node.col}: unsupported print type")
def _p7_assignment_sem(self, node):
    _old_semantic_assign(self, node)
    if self.current_function and isinstance(self.current_function, MemberFnNode):
        if isinstance(node.decl, FieldDeclNode):
            self.current_function.direct_mutating = True
        elif node.resolved_fields and isinstance(node.decl, FieldDeclNode):
            self.current_function.direct_mutating = True
SemanticChecker.lookup = _p7_lookup
SemanticChecker.visit_structdecl = _p7_struct_sem
SemanticChecker.visit_program = _p7_program_sem
SemanticChecker.visit_functiondecl = _p7_function_sem
SemanticChecker.visit_memberfn = _p7_function_sem
SemanticChecker.visit_var = _p7_var_sem
SemanticChecker.visit_fieldaccess = _p7_field_sem
SemanticChecker.visit_call = _p7_call_sem
SemanticChecker.visit_membercall = _p7_membercall_sem
SemanticChecker.visit_resultfield = _p7_resultfield_sem
SemanticChecker.visit_string = _p7_string_sem
SemanticChecker.visit_print = _p7_print_sem
SemanticChecker.visit_assign = _p7_assignment_sem
# IR additions use llvmlite.ir only. In particular no LLVM IR strings
# are assembled by hand.
_old_codegen_program = CodeGen.visit_program
_old_codegen_function = CodeGen.visit_functiondecl
_old_codegen_var = CodeGen.visit_var
_old_codegen_field = CodeGen.visit_fieldaccess
_old_codegen_call = CodeGen.visit_call
_old_codegen_assign = CodeGen.visit_assign
def _p7_generate_program(self, node):
    self.struct_decls = {s.name: s for s in node.structs}
    for struct in node.structs:
        t = self.module.context.get_identified_type(struct.name)
        self.struct_types[struct.name] = t
        struct.llvm_type = t
    for struct in node.structs:
        struct.llvm_type.set_body(*[llvm_type(f.type_name, self.struct_types) for f in struct.fields])
    all_fns = node.functions + [m for s in node.structs for m in s.member_functions]
    for fn in all_fns:
        params = [llvm_type(p.type_name, self.struct_types) for p in fn.params]
        if isinstance(fn, MemberFnNode):
            params.insert(0, llvm_type(fn.owner.name, self.struct_types).as_pointer())
            name = f"{fn.owner.name}_{fn.name}"
        else:
            name = f"user_fn_{fn.name}"
        fn.llvm_function = ir.Function(self.module, ir.FunctionType(llvm_type(fn.result_type, self.struct_types), params), name=name)
    for fn in all_fns:
        fn.accept(self)
    self.current_function_decl = None
    self.current_ir_function = self.main
    self.entry = self.main.entry_basic_block
    self.builder = ir.IRBuilder(self.entry)
    self.builder.position_at_end(self.entry)
    for stmt in node.statements:
        if not self.builder.block.is_terminated:
            stmt.accept(self)
    if not self.builder.block.is_terminated:
        node.exit_node.accept(self)
def _p7_codegen_function(self, node):
    old_builder = self.builder
    old_entry = self.entry
    old_ir = self.current_ir_function
    old_decl = self.current_function_decl
    old_this = getattr(self, "this_ptr", None)
    fn = node.llvm_function
    entry = fn.append_basic_block("entry")
    self.current_ir_function = fn
    self.current_function_decl = node
    self.entry = entry
    self.builder = ir.IRBuilder(entry)
    args = list(fn.args)
    self.this_ptr = None
    if isinstance(node, MemberFnNode):
        self.this_ptr = args.pop(0)
        self.this_ptr.name = "this"
    for arg, param in zip(args, node.params):
        arg.name = param.name
        ptr = self.create_alloca(param.type_name, param.name)
        self.builder.store(arg, ptr)
        param.ptr = ptr
    node.body.accept(self)
    self.builder = old_builder
    self.entry = old_entry
    self.current_ir_function = old_ir
    self.current_function_decl = old_decl
    self.this_ptr = old_this
def _p7_declaration_pointer(self, node):
    if isinstance(node.decl, FieldDeclNode):
        return self.builder.gep(self.this_ptr, [ir.Constant(I32, 0), ir.Constant(I32, node.decl.index)], inbounds=True)
    return node.decl.ptr
def _p7_expression_pointer(self, node):
    if isinstance(node, VarNode):
        return _p7_declaration_pointer(self, node)
    if isinstance(node, FieldAccessNode):
        ptr = _p7_declaration_pointer(self, node)
        for field in node.resolved_fields:
            ptr = self.builder.gep(ptr, [ir.Constant(I32, 0), ir.Constant(I32, field.index)], inbounds=True)
        return ptr
    if isinstance(node, ResultFieldNode):
        ptr = _p7_expression_pointer(self, node.receiver)
        return self.builder.gep(ptr, [ir.Constant(I32, 0), ir.Constant(I32, node.field.index)], inbounds=True)
    if node.type in self.struct_types:
        ptr = self.create_alloca(node.type, "temporary")
        self.builder.store(node.accept(self), ptr)
        return ptr
    raise CompileError(f"line {node.line}:{node.col}: expression is not an object")
def _p7_codegen_var(self, node):
    return self.builder.load(_p7_declaration_pointer(self, node), name=f"load_{node.name}")
def _p7_codegen_field(self, node):
    return self.builder.load(_p7_expression_pointer(self, node), name=f"load_{node.name}_{'_'.join(node.fields)}")
def _p7_codegen_resultfield(self, node):
    return self.builder.load(_p7_expression_pointer(self, node))
def _p7_call_values(self, args, params):
    values = []
    for arg, param in zip(args, params):
        value = arg.accept(self)
        values.append(self.coerce(value, arg.type, param.type_name))
    return values
def _p7_codegen_call(self, node):
    if node.function == "read":
        if not hasattr(self, "scanf"):
            scanf_t = ir.FunctionType(I32, [I8.as_pointer()], var_arg=True)
            self.scanf = ir.Function(self.module, scanf_t, name="scanf")
        tmp = self.create_alloca("i32", "read_value")
        self.builder.call(self.scanf, [self._p7_string("%d"), tmp])
        return self.builder.load(tmp)
    if isinstance(node.function, MemberFnNode):
        vals = [self.this_ptr] + _p7_call_values(self, node.args, node.function.params)
        return self.builder.call(node.function.llvm_function, vals)
    return _old_codegen_call(self, node)
def _p7_codegen_membercall(self, node):
    ptr = _p7_expression_pointer(self, node.receiver)
    values = [ptr] + _p7_call_values(self, node.args, node.function.params)
    return self.builder.call(node.function.llvm_function, values)
def _p7_codegen_assign(self, node):
    if not isinstance(node.decl, FieldDeclNode):
        return _old_codegen_assign(self, node)
    val = node.value.accept(self)
    val = self.coerce(val, node.value.type, node.target_type)
    ptr = self.builder.gep(self.this_ptr, [ir.Constant(I32, 0), ir.Constant(I32, node.decl.index)], inbounds=True)
    for field in node.resolved_fields:
        ptr = self.builder.gep(ptr, [ir.Constant(I32, 0), ir.Constant(I32, field.index)], inbounds=True)
    self.builder.store(val, ptr)
def _p7_string(self, text):
    if not hasattr(self, "p7_strings"):
        self.p7_strings = {}
    if text not in self.p7_strings:
        raw = text.encode("utf-8") + b"\0"
        self.p7_strings[text] = self.make_string(f"p7_string_{len(self.p7_strings)}", raw)
    return self.string_ptr(self.p7_strings[text])
def _p7_printf(self, fmt, *values):
    self.builder.call(self.printf, [self._p7_string(fmt), *values])
def _p7_print_struct(self, ptr, type_name):
    struct = self.struct_decls[type_name]
    _p7_printf(self, "%s", self._p7_string(type_name + "{"))
    for index, field in enumerate(struct.fields):
        if index:
            _p7_printf(self, "%s", self._p7_string(", "))
        _p7_printf(self, "%s", self._p7_string(field.name + ": "))
        fptr = self.builder.gep(ptr, [ir.Constant(I32, 0), ir.Constant(I32, index)], inbounds=True)
        if field.type_name in self.struct_types:
            _p7_print_struct(self, fptr, field.type_name)
        elif field.type_name == "bool":
            val = self.builder.load(fptr)
            text = self.builder.select(val, self._p7_string("true"), self._p7_string("false"))
            _p7_printf(self, "%s", text)
        else:
            _p7_printf(self, "%d" if field.type_name == "i32" else "%lld", self.builder.load(fptr))
    _p7_printf(self, "%s", self._p7_string("}"))
def _p7_codegen_print(self, node):
    expr = node.value
    if expr.type == "string":
        _p7_printf(self, "%s\n", self._p7_string(expr.value))
    elif expr.type == "bool":
        val = expr.accept(self)
        _p7_printf(self, "%s\n", self.builder.select(val, self._p7_string("true"), self._p7_string("false")))
    elif expr.type in INT_TYPES:
        _p7_printf(self, "%d\n" if expr.type == "i32" else "%lld\n", expr.accept(self))
    else:
        ptr = _p7_expression_pointer(self, expr)
        _p7_print_struct(self, ptr, expr.type)
        _p7_printf(self, "%s", self._p7_string("\n"))
CodeGen.visit_program = _p7_generate_program
CodeGen.visit_functiondecl = _p7_codegen_function
CodeGen.visit_memberfn = _p7_codegen_function
CodeGen.visit_var = _p7_codegen_var
CodeGen.visit_fieldaccess = _p7_codegen_field
CodeGen.visit_resultfield = _p7_codegen_resultfield
CodeGen.visit_call = _p7_codegen_call
CodeGen.visit_membercall = _p7_codegen_membercall
CodeGen.visit_assign = _p7_codegen_assign
CodeGen.visit_print = _p7_codegen_print
CodeGen._p7_string = _p7_string
if __name__ == "__main__":
    main()
