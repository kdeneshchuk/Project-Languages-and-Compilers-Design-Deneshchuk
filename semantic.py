"""Telly semantic pass: a symbol table and the checks described in README.md."""

from lexer import CompileError
from ast_nodes import *

INT_MAX = 2147483647


def fits(have, want):
    """May a value of type `have` go where `want` is expected? The same type, or int into long."""
    return have == want or (have == "int" and want == "long")


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
        self.tasks = {}                 # task name -> TaskNode: the signatures
        self.global_consts = {}         # top-level "always" constants, seen by every task
        self.top_level_vars = set()     # names of top-level "once" variables (for a clear error)
        self.current_task = None        # the task whose body is being checked

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
        if self.current_task is not None:       # inside a task: then the global constants
            return self.global_consts.get(name)
        return None

    def unknown(self, node, name):
        if self.current_task is not None and name in self.top_level_vars:
            self.fail(node, f"variable '{name}' of the top level is not visible inside a task")
        self.fail(node, f"variable '{name}' is used before its declaration")

    def declare(self, node, symbol):
        if symbol.name in self.scopes[-1]:
            self.fail(node, f"'{symbol.name}' is already declared in this scope")
        self.scopes[-1][symbol.name] = symbol

    def check_assignable(self, expr, want, at, what):
        have = expr.type
        if fits(have, want):
            return
        if isinstance(expr, NumberNode) and want in ("int", "long"):
            self.fail(expr, f"number {expr.value} does not fit in {want}")
        self.fail(at, f"cannot {what} of type {want} with a value of type {have}")

    # ---------- collecting: before any body is checked ----------

    def collect_top_level(self, statements):
        for stmt in statements:
            if isinstance(stmt, VarDeclNode):
                self.top_level_vars.add(stmt.name)
            elif isinstance(stmt, ConstDeclNode):
                self.visit(stmt.value)
                self.check_assignable(stmt.value, stmt.type_name, stmt, f"initialise '{stmt.name}'")
                if stmt.name in self.global_consts:
                    self.fail(stmt, f"'{stmt.name}' is already declared in this scope")
                stmt.symbol = Symbol(stmt.name, stmt.type_name, False, "const")
                self.global_consts[stmt.name] = stmt.symbol

    def collect_tasks(self, tasks):
        for task in tasks:
            if task.name in self.tasks:
                self.fail(task, f"task '{task.name}' is already declared")
            seen = set()
            for p in task.params:
                if p.name in seen:
                    self.fail(p, f"parameter '{p.name}' is already declared in task '{task.name}'")
                seen.add(p.name)
            self.tasks[task.name] = task

    # ---------- program, tasks and blocks ----------

    def visit_ProgramNode(self, node):
        for struct in node.structs:
            self.visit(struct)          # no method yet: "not supported yet"
        self.collect_top_level(node.statements)
        self.collect_tasks(node.tasks)
        for task in node.tasks:
            self.visit(task)
        for stmt in node.statements:
            self.visit(stmt)
        self.visit(node.tell)

    def visit_TaskNode(self, node):
        saved = (self.scopes, self.current_task)
        frame = {}
        for p in node.params:
            p.symbol = Symbol(p.name, p.type_name, False, "var")
            frame[p.name] = p.symbol
        self.scopes = [frame]           # the bottom frame holds only the parameters
        self.current_task = node
        self.visit(node.body)           # the body pushes its own frame on top
        self.scopes, self.current_task = saved

    def visit_BlockNode(self, node):
        self.scopes.append({})
        for stmt in node.statements:
            self.visit(stmt)
        self.scopes.pop()

    # ---------- statements ----------

    def visit_ConstDeclNode(self, node):
        if not hasattr(node, "symbol"):             # a top-level one was made when collecting
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
        if len(node.names) > 1:
            self.fail(node, "this construct is not supported yet")
        name = node.names[0]
        symbol = self.lookup(name)
        if symbol is None:
            self.unknown(node, name)
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

    def visit_GiveNode(self, node):
        task = self.current_task
        value_type = self.visit(node.value)
        if not fits(value_type, task.result_type):
            if isinstance(node.value, NumberNode) and task.result_type in ("int", "long"):
                self.fail(node.value, f"number {node.value.value} does not fit in {task.result_type}")
            self.fail(node, f"task '{task.name}' gives {task.result_type}, "
                            f"but this value has type {value_type}")

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
            self.unknown(node, node.name)
        node.symbol = symbol
        node.type = symbol.type_name
        return node.type

    def visit_CallNode(self, node):
        task = self.tasks.get(node.name)
        if task is None:
            self.fail(node, f"task '{node.name}' is not declared")
        if len(node.args) != len(task.params):
            self.fail(node, f"task '{node.name}' takes {len(task.params)} "
                            f"argument(s), got {len(node.args)}")
        for i, (arg, param) in enumerate(zip(node.args, task.params), 1):
            self.visit(arg)
            self.check_assignable(arg, param.type_name, arg, f"pass argument {i} of '{node.name}'")
        node.task = task
        node.type = task.result_type
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