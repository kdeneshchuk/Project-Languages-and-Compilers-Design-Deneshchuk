"""Telly semantic pass: a symbol table and the checks described in README.md."""

from lexer import CompileError
from ast_nodes import *

INT_MAX = 2147483647


class Symbol:
    """What the checker knows about one name."""
    def __init__(self, name, type_name, mutable, kind):
        self.name = name
        self.type_name = type_name      # "int", "long", "flag"
        self.mutable = mutable          # True only for "once changing"
        self.kind = kind                # "const" or "var"
        self.const = None               # set by the code generator: the value of a constant
        self.ptr = None                 # set by the code generator: the slot of a variable


class SemanticChecker:
    def __init__(self):
        self.scopes = [{}]              # a stack of frames; the bottom one is the top level

    def check(self, tree):
        self.visit(tree)

    def visit(self, node):
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            self.fail(node, "this construct is not supported yet")
        return method(node)

    def fail(self, at, msg):
        raise CompileError(f"line {at.line}:{at.col}: {msg}")

    # ---------- symbol table ----------

    def lookup(self, name):
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name]
        return None

    def declare(self, node, symbol):
        if symbol.name in self.scopes[-1]:
            self.fail(node, f"'{symbol.name}' is already declared in this scope")
        self.scopes[-1][symbol.name] = symbol

    def check_assignable(self, expr, want, at, what):
        have = expr.type
        if have == want or (have == "int" and want == "long"):
            return
        if isinstance(expr, NumberNode) and want in ("int", "long"):
            self.fail(expr, f"number {expr.value} does not fit in {want}")
        self.fail(at, f"cannot {what} of type {want} with a value of type {have}")

    # ---------- program and blocks ----------

    def visit_ProgramNode(self, node):
        for item in node.structs + node.tasks:
            self.visit(item)
        for stmt in node.statements:
            self.visit(stmt)
        self.visit(node.tell)

    def visit_BlockNode(self, node):
        self.scopes.append({})
        for stmt in node.statements:
            self.visit(stmt)
        self.scopes.pop()

    # ---------- statements ----------

    def visit_ConstDeclNode(self, node):
        self.visit(node.value)
        self.check_assignable(node.value, node.type_name, node, f"initialise '{node.name}'")
        node.symbol = Symbol(node.name, node.type_name, False, "const")
        self.declare(node, node.symbol)

    def visit_VarDeclNode(self, node):
        self.visit(node.init)
        self.check_assignable(node.init, node.type_name, node, f"initialise '{node.name}'")
        node.symbol = Symbol(node.name, node.type_name, node.mutable, "var")
        self.declare(node, node.symbol)

    def visit_AssignNode(self, node):
        name = node.names[0]
        symbol = self.lookup(name)
        if symbol is None:
            self.fail(node, f"variable '{name}' is used before its declaration")
        if not symbol.mutable:
            self.fail(node, f"cannot assign to '{name}': it is not 'once changing'")
        self.visit(node.value)
        self.check_assignable(node.value, symbol.type_name, node, f"assign to '{name}'")
        node.symbol = symbol

    def visit_WhenNode(self, node):
        cond_type = self.visit(node.cond)
        if cond_type != "flag":
            self.fail(node, f"the condition of 'when' must be a flag, got {cond_type}")
        self.visit(node.then_block)
        if node.else_block is not None:
            self.visit(node.else_block)

    def visit_TellNode(self, node):
        self.visit(node.value)

    # ---------- expressions: every visit sets node.type and returns it ----------

    def visit_NumberNode(self, node):
        node.type = "int" if node.value <= INT_MAX else "long"
        return node.type

    def visit_BoolNode(self, node):
        node.type = "flag"
        return node.type

    def visit_VarNode(self, node):
        symbol = self.lookup(node.name)
        if symbol is None:
            self.fail(node, f"variable '{node.name}' is used before its declaration")
        node.symbol = symbol
        node.type = symbol.type_name
        return node.type

    def visit_BinOpNode(self, node):
        lt = self.visit(node.left)
        rt = self.visit(node.right)
        if node.op in ("+", "-", "*"):
            if "flag" in (lt, rt):
                self.fail(node, f"cannot apply '{node.op}' to flag")
            node.type = "long" if "long" in (lt, rt) else "int"
            node.operand_type = node.type
        else:
            if (lt == "flag") != (rt == "flag"):
                self.fail(node, f"cannot compare {lt} with {rt}")
            node.operand_type = "flag" if lt == "flag" else ("long" if "long" in (lt, rt) else "int")
            node.type = "flag"
        return node.type