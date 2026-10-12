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
if __name__ == "__main__":
    main()
