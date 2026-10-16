"""Telly parser: recursive descent, one function per grammar rule."""

from lexer import CompileError, number_value, MAX_LONG
from ast_nodes import *

TRUE_TEXTS = ("yes", "\U0001F44D")
EQ_TEXTS = ("equals", "\U0001F7F0")
INT_MAX = 2147483647
MAX_DEPTH = 100

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.depth = 0

    # ---------- primitives ----------

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def eat(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def error(self, msg, at=None):
        tok = at if at is not None else self.peek()
        if tok is not None:
            raise CompileError(f"line {tok.line}:{tok.col}: {msg}")
        if self.tokens:                      # end of file: just after the last token
            last = self.tokens[-1]
            col = last.col + len(last.text.encode())
            raise CompileError(f"line {last.line}:{col}: {msg}")
        raise CompileError(f"line 1:1: {msg}")

    def expect(self, kind, what, text=None):
        tok = self.peek()
        if tok is None:
            self.error(f"expected {what}, found end of file")
        if tok.kind != kind or (text is not None and tok.text != text):
            self.error(f"expected {what}, got '{tok.text}'")
        return self.eat()

    # ---------- expressions ----------

    def parse_boolean(self):                 # boolean ::= "yes" | "no" | "👍" | "👎"
        tok = self.expect("bool", "yes, no or an emoji truth value")
        return BoolNode(tok.line, tok.col, tok.text in TRUE_TEXTS)

    def parse_compare_op(self):              # compare_op ::= "equals" | "differs" | "🟰" | "🚫"
        tok = self.expect("cmp", "a comparison (equals or differs)")
        return tok, ("==" if tok.text in EQ_TEXTS else "!=")

    def parse_factor(self):                  # factor ::= number | boolean | ident
        tok = self.peek()
        if tok is None:
            self.error("expected a number, a truth value or a name, found end of file")
        if tok.kind == "number":
            self.eat()
            return NumberNode(tok.line, tok.col, number_value(tok.text))
        if tok.kind == "bool":
            return self.parse_boolean()
        if tok.kind == "ident":
            self.eat()
            return VarNode(tok.line, tok.col, tok.text)
        self.error(f"expected a number, a truth value or a name, got '{tok.text}'")

    def parse_term(self):                    # term ::= factor { "*" factor }
        node = self.parse_factor()
        while (tok := self.peek()) is not None and tok.kind == "op" and tok.text == "*":
            self.eat()
            node = BinOpNode(tok.line, tok.col, "*", node, self.parse_factor())
        return node

    def parse_arith(self):                   # arith ::= term { ("+" | "-") term }
        node = self.parse_term()
        while (tok := self.peek()) is not None and tok.kind == "op" and tok.text in ("+", "-"):
            self.eat()
            node = BinOpNode(tok.line, tok.col, tok.text, node, self.parse_term())
        return node

    def parse_expr(self):                    # expr ::= arith [ compare_op arith ]
        node = self.parse_arith()
        tok = self.peek()
        if tok is not None and tok.kind == "cmp":
            op_tok, op = self.parse_compare_op()
            node = BinOpNode(op_tok.line, op_tok.col, op, node, self.parse_arith())
        return node

    # ---------- types and literals ----------

    def parse_type(self):                    # type ::= "int" | "long" | "flag"
        tok = self.expect("type", "a type (int, long or flag)")
        return tok.text

    def parse_literal(self):                 # literal ::= number | boolean
        tok = self.peek()
        if tok is not None and tok.kind == "number":
            self.eat()
            return NumberNode(tok.line, tok.col, number_value(tok.text))
        if tok is not None and tok.kind == "bool":
            return self.parse_boolean()
        if tok is None:
            self.error("expected a number or a truth value, found end of file")
        self.error(f"expected a number or a truth value, got '{tok.text}'")

    def check_range(self, type_name, node):
        """Stage 1 overflow check: only a bare number literal next to its type."""
        if not isinstance(node, NumberNode):
            return
        limit = INT_MAX if type_name == "int" else MAX_LONG
        if type_name in ("int", "long") and node.value > limit:
            raise CompileError(
                f"line {node.line}:{node.col}: number {node.value} does not fit in {type_name}")

    # ---------- statements ----------

    def parse_const_decl(self):              # "always" type ident "is" literal "."
        self.eat()                           # "always", the caller looked at it
        type_name = self.parse_type()
        name = self.expect("ident", "a variable name")
        self.expect("kw", "'is'", "is")
        value = self.parse_literal()
        self.check_range(type_name, value)
        self.expect("dot", "'.'")
        return ConstDeclNode(name.line, name.col, name.text, type_name, value)

    def parse_var_decl(self):                # "once" ["changing"] type ident "was" expr "."
        self.eat()                           # "once"
        tok = self.peek()
        mutable = tok is not None and tok.kind == "kw" and tok.text == "changing"
        if mutable:
            self.eat()
        type_name = self.parse_type()
        name = self.expect("ident", "a variable name")
        self.expect("kw", "'was'", "was")
        init = self.parse_expr()
        self.check_range(type_name, init)
        self.expect("dot", "'.'")
        return VarDeclNode(name.line, name.col, name.text, type_name, mutable, init)

    def parse_assign(self):                  # ident "became" expr "."
        name = self.eat()                    # the identifier
        self.expect("kw", "'became'", "became")
        value = self.parse_expr()
        self.expect("dot", "'.'")
        return AssignNode(name.line, name.col, name.text, value)

    def parse_tell(self):                    # "tell" factor "."
        tell = self.eat()
        value = self.parse_factor()
        self.expect("dot", "'.'")
        return TellNode(tell.line, tell.col, value)


    # ---------- blocks, when, program ----------

    def starts_statement(self, tok):
        if tok is None:
            return False
        if tok.kind == "ident":
            return True
        return tok.kind == "kw" and tok.text in ("always", "once", "when")

    def parse_statement(self):               # const_decl | var_decl | assign | when_stmt
        tok = self.peek()
        if tok.kind == "kw" and tok.text == "always":
            return self.parse_const_decl()
        if tok.kind == "kw" and tok.text == "once":
            return self.parse_var_decl()
        if tok.kind == "kw" and tok.text == "when":
            return self.parse_when()
        if tok.kind == "ident":
            return self.parse_assign()
        self.error(f"cannot start a statement with '{tok.text}'")

    def parse_block(self):                   # block ::= statement { statement }
        first = self.peek()
        if not self.starts_statement(first):
            if first is None:
                self.error("expected a statement, found end of file")
            self.error(f"expected a statement, got '{first.text}'")
        line, col = first.line, first.col
        statements = [self.parse_statement()]
        while self.starts_statement(self.peek()):
            statements.append(self.parse_statement())
        return BlockNode(line, col, statements)

    def parse_when(self):                    # "when" expr ":" block ["otherwise" ":" block] "end" "."
        when = self.eat()
        self.depth += 1
        if self.depth > MAX_DEPTH:
            self.error(f"'when' is nested deeper than {MAX_DEPTH} levels", at=when)
        cond = self.parse_expr()
        self.expect("colon", "':'")
        then_block = self.parse_block()
        else_block = None
        tok = self.peek()
        if tok is not None and tok.kind == "kw" and tok.text == "otherwise":
            self.eat()
            self.expect("colon", "':'")
            else_block = self.parse_block()
        self.expect("kw", "'end'", "end")
        self.expect("dot", "'.'")
        self.depth -= 1
        return WhenNode(when.line, when.col, cond, then_block, else_block)

    def parse_program(self):                 # program ::= { statement } tell_stmt
        statements = []
        while self.starts_statement(self.peek()):
            statements.append(self.parse_statement())
        tok = self.peek()
        if tok is None:
            self.error("expected 'tell' at the end of the program, found end of file")
        if not (tok.kind == "kw" and tok.text == "tell"):
            self.error(f"cannot start a statement with '{tok.text}'")
        tell = self.parse_tell()
        extra = self.peek()
        if extra is not None:
            self.error(f"unexpected '{extra.text}' after 'tell'")
        return ProgramNode(1, 1, statements, tell)