"""Telly parser: recursive descent, one function per grammar rule."""

from lexer import CompileError, number_value, MAX_LONG
from ast_nodes import *

TRUE_TEXTS = ("yes", "\U0001F44D")
EQ_TEXTS = ("equals", "\U0001F7F0")
INT_MAX = 2147483647
MAX_DEPTH = 100
MAX_EXPR_DEPTH = 100

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.depth = 0
        self.in_task = False
        self.struct_names = set()
        self.expr_depth = 0

    # ---------- primitives ----------

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def peek_next(self):
        return self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None

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
            col = last.col + last.length
            raise CompileError(f"line {last.line}:{col}: {msg}")
        raise CompileError(f"line 1:1: {msg}")

    def expect(self, kind, what, text=None):
        tok = self.peek()
        if tok is None:
            self.error(f"expected {what}, found end of file")
        if tok.kind != kind or (text is not None and tok.text != text):
            self.error(f"expected {what}, got '{tok.text}'")
        return self.eat()

    def expect_name(self, what):
        tok = self.peek()
        if tok is not None and tok.kind == "kw" and tok.text in ("read", "print"):
            self.error(f"'{tok.text}' is a built-in name and cannot be used as {what}")
        return self.expect("ident", what)

    # ---------- expressions ----------

    def parse_boolean(self):                 # boolean ::= "yes" | "no" | "👍" | "👎"
        tok = self.expect("bool", "yes, no or an emoji truth value")
        return BoolNode(tok.line, tok.col, tok.text in TRUE_TEXTS)

    def parse_compare_op(self):              # compare_op ::= "equals" | "differs" | "🟰" | "🚫"
        tok = self.expect("cmp", "a comparison (equals or differs)")
        return tok, ("==" if tok.text in EQ_TEXTS else "!=")

    def parse_names(self):                   # ident { "of" ident }
        first = self.expect("ident", "a name")
        names = [first.text]
        while (tok := self.peek()) is not None and tok.kind == "kw" and tok.text == "of":
            self.eat()
            names.append(self.expect("ident", "a name after 'of'").text)
        return first, names

    def parse_access(self):                  # access ::= ident { "of" ident }
        first, names = self.parse_names()
        if len(names) == 1:
            return VarNode(first.line, first.col, first.text)
        return FieldNode(first.line, first.col, names)

    def parse_args(self, allow_empty=True):  # "(" [ expr { "," expr } ] ")"
        self.expect("lparen", "'('")
        args = []
        tok = self.peek()
        if not (allow_empty and tok is not None and tok.kind == "rparen"):
            args.append(self.parse_expr())
            while (tok := self.peek()) is not None and tok.kind == "comma":
                self.eat()
                args.append(self.parse_expr())
        self.expect("rparen", "')'")
        return args

    def parse_call(self):                    # ident "(" args ")" [ "of" access ]
        name = self.eat()
        args = self.parse_args()
        tok = self.peek()
        if tok is not None and tok.kind == "kw" and tok.text == "of":
            self.eat()
            _, obj = self.parse_names()
            return MemberCallNode(name.line, name.col, name.text, args, obj)
        return CallNode(name.line, name.col, name.text, args)

    def parse_make(self):                    # "make" ident "(" expr { "," expr } ")"
        make = self.eat()
        name = self.expect("ident", "a struct name")
        args = self.parse_args(allow_empty=False)
        return MakeNode(make.line, make.col, name.text, args)

    def parse_read(self):                    # "read" "(" ")"
        read = self.eat()
        self.expect("lparen", "'(' after 'read'")
        self.expect("rparen", "')'")
        return ReadNode(read.line, read.col)

    def parse_factor(self):                  # number | boolean | read | make | call | access
        tok = self.peek()
        if tok is None:
            self.error("expected a number, a truth value or a name, found end of file")
        if tok.kind == "number":
            self.eat()
            return NumberNode(tok.line, tok.col, number_value(tok.text))
        if tok.kind == "bool":
            return self.parse_boolean()
        if tok.kind == "kw" and tok.text == "read":
            return self.parse_read()
        if tok.kind == "kw" and tok.text == "make":
            return self.parse_make()
        if tok.kind == "ident":
            nxt = self.peek_next()
            if nxt is not None and nxt.kind == "lparen":
                return self.parse_call()
            return self.parse_access()
        if tok.kind == "string":
            self.error("a string literal can only be the argument of 'print'")
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
        self.expr_depth += 1
        if self.expr_depth > MAX_EXPR_DEPTH:
            self.error(f"expression is nested deeper than {MAX_EXPR_DEPTH} levels")
        node = self.parse_arith()
        tok = self.peek()
        if tok is not None and tok.kind == "cmp":
            op_tok, op = self.parse_compare_op()
            node = BinOpNode(op_tok.line, op_tok.col, op, node, self.parse_arith())
        self.expr_depth -= 1
        return node

    # ---------- types and literals ----------

    def parse_builtin_type(self):            # builtin_type ::= "int" | "long" | "flag"
        tok = self.expect("type", "a type (int, long or flag)")
        return tok.text

    def parse_type(self):                    # type ::= builtin_type | ident (a struct)
        tok = self.peek()
        if tok is not None and tok.kind == "ident" and tok.text in self.struct_names:
            self.eat()
            return tok.text
        return self.parse_builtin_type()

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
        type_name = self.parse_builtin_type()
        name = self.expect_name("a variable name")
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
        name = self.expect_name("a variable name")
        self.expect("kw", "'was'", "was")
        init = self.parse_expr()
        self.check_range(type_name, init)
        self.expect("dot", "'.'")
        return VarDeclNode(name.line, name.col, name.text, type_name, mutable, init)

    def parse_assign(self):                  # access "became" expr "."
        first, names = self.parse_names()
        self.expect("kw", "'became'", "became")
        value = self.parse_expr()
        self.expect("dot", "'.'")
        return AssignNode(first.line, first.col, names, value)

    def parse_print(self):                   # "print" "(" ( string | expr ) ")" "."
        print_tok = self.eat()
        self.expect("lparen", "'(' after 'print'")
        tok = self.peek()
        if tok is not None and tok.kind == "string":
            self.eat()
            value = StringNode(tok.line, tok.col, tok.text)
        else:
            value = self.parse_expr()
        self.expect("rparen", "')'")
        self.expect("dot", "'.'")
        return PrintNode(print_tok.line, print_tok.col, value)

    def parse_give(self):                    # "give" factor "."
        give = self.eat()
        if not self.in_task:
            self.error("'give' can only stand inside a task", at=give)
        value = self.parse_factor()
        self.expect("dot", "'.'")
        return GiveNode(give.line, give.col, value)

    def parse_param(self):                   # param ::= type ident
        type_name = self.parse_type()
        name = self.expect_name("a parameter name")
        return ParamNode(name.line, name.col, name.text, type_name)

    def parse_task(self, is_member=False):   # "task" ident "(" ... ")" "giving" type ":" block "end" "."
        self.eat()                           # "task"
        name = self.expect_name("a task name")
        self.expect("lparen", "'('")
        params = []
        tok = self.peek()
        if not (tok is not None and tok.kind == "rparen"):
            params.append(self.parse_param())
            while (tok := self.peek()) is not None and tok.kind == "comma":
                self.eat()
                params.append(self.parse_param())
        self.expect("rparen", "')'")
        self.expect("kw", "'giving'", "giving")
        result_type = self.parse_type()
        self.expect("colon", "':'")
        saved = self.in_task
        self.in_task = True
        body = self.parse_block()
        self.in_task = saved
        if not isinstance(body.statements[-1], GiveNode):
            self.error("the body of a task must end with 'give'")
        self.expect("kw", "'end'", "end")
        self.expect("dot", "'.'")
        return TaskNode(name.line, name.col, name.text, params, result_type, body, is_member)

    def parse_field_decl(self):              # "once" ["changing"] type ident "."
        self.eat()                           # "once"
        tok = self.peek()
        mutable = tok is not None and tok.kind == "kw" and tok.text == "changing"
        if mutable:
            self.eat()
        type_name = self.parse_type()
        name = self.expect_name("a field name")
        self.expect("dot", "'.'")
        return FieldDeclNode(name.line, name.col, name.text, type_name, mutable)

    def parse_struct(self):                  # "struct" ident ":" field { field } { task } "end" "."
        self.eat()                           # "struct"
        name = self.expect_name("a struct name")
        self.struct_names.add(name.text)
        self.expect("colon", "':'")
        fields, tasks = [], []
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "kw" and tok.text == "once":
                if tasks:
                    self.error("a field cannot come after a member function")
                fields.append(self.parse_field_decl())
            elif tok is not None and tok.kind == "kw" and tok.text == "task":
                if not fields:
                    self.error("a member function cannot come before the first field")
                tasks.append(self.parse_task(is_member=True))
            else:
                break
        if not fields:
            self.error("a struct needs at least one field")
        self.expect("kw", "'end'", "end")
        self.expect("dot", "'.'")
        return StructNode(name.line, name.col, name.text, fields, tasks)

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
        return tok.kind == "kw" and tok.text in ("always", "once", "when", "print", "give")

    def starts_with(self, word):
        tok = self.peek()
        return tok is not None and tok.kind == "kw" and tok.text == word

    def parse_statement(self):               # const_decl | var_decl | assign | when_stmt
        tok = self.peek()
        if tok.kind == "kw" and tok.text == "always":
            return self.parse_const_decl()
        if tok.kind == "kw" and tok.text == "once":
            return self.parse_var_decl()
        if tok.kind == "kw" and tok.text == "when":
            return self.parse_when()
        if tok.kind == "kw" and tok.text == "print":
            return self.parse_print()
        if tok.kind == "kw" and tok.text == "give":
            return self.parse_give()
        if tok.kind == "ident":
            nxt = self.peek_next()
            if nxt is not None and nxt.kind == "lparen":
                self.error("a call alone is not a statement", at=tok)
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
            if isinstance(statements[-1], GiveNode):
                self.error("nothing may follow 'give' in the same block")
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

    def parse_program(self):                 # program ::= { struct } { task } { statement } tell_stmt
        structs, tasks, statements = [], [], []
        while self.starts_with("struct"):
            structs.append(self.parse_struct())
        while self.starts_with("task"):
            tasks.append(self.parse_task())
        while self.starts_statement(self.peek()):
            statements.append(self.parse_statement())
        tok = self.peek()
        if tok is None:
            self.error("expected 'tell' at the end of the program, found end of file")
        if tok.kind == "kw" and tok.text == "struct":
            self.error("a struct must be declared before the tasks and the statements")
        if tok.kind == "kw" and tok.text == "task":
            self.error("a task must be declared before the statements")
        if not (tok.kind == "kw" and tok.text == "tell"):
            self.error(f"cannot start a statement with '{tok.text}'")
        tell = self.parse_tell()
        extra = self.peek()
        if extra is not None:
            self.error(f"unexpected '{extra.text}' after 'tell'")
        return ProgramNode(1, 1, statements, tell, structs, tasks)