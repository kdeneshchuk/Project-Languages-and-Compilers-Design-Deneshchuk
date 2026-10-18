"""Telly semantic pass: a symbol table and the checks described in README.md."""

from lexer import CompileError
from ast_nodes import *

INT_MAX = 2147483647


def fits(have, want):
    """May a value of type `have` go where `want` is expected? The same type, or int into long."""
    return have == want or (have == "int" and want == "long")


class At:
    """A bare position, for an error on one name of a chain."""
    def __init__(self, pos):
        self.line, self.col = pos


class Symbol:
    """What the checker knows about one name."""
    def __init__(self, name, type_name, mutable, kind):
        self.name = name
        self.type_name = type_name      # "int", "long", "flag" or the name of a struct
        self.mutable = mutable          # True only for "once changing"
        self.kind = kind                # "const" or "var"
        self.const = None               # set by the code generator: the value of a constant
        self.ptr = None                 # set by the code generator: the slot of a variable


class FieldInfo:
    def __init__(self, name, type_name, mutable, index):
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.index = index              # the position in the struct: what the gep uses


class StructInfo:
    def __init__(self, name, fields):
        self.name = name
        self.fields = fields            # in the order of the declaration
        self.by_name = {f.name: f for f in fields}


class SemanticChecker:
    def __init__(self):
        self.scopes = [{}]              # a stack of frames; the bottom one is the top level
        self.structs = {}               # struct name -> StructInfo
        self.struct_names = set()       # the names of all the structs, known before any is checked
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

    def check_not_struct(self, node, name):
        if name in self.struct_names:
            self.fail(node, f"'{name}' is the name of a struct")

    def declare(self, node, symbol):
        self.check_not_struct(node, symbol.name)
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

    def resolve_chain(self, names, positions):
        """`x of center of c`: the variable is the last name, the fields follow from the inside out.
        Returns the symbol, the list of fields passed, their indexes and the type of the end."""
        symbol = self.lookup(names[-1])
        if symbol is None:
            self.unknown(At(positions[-1]), names[-1])
        t = symbol.type_name
        links, path = [], []
        for i in range(len(names) - 2, -1, -1):
            fname, where = names[i], At(positions[i])
            if t not in self.structs:
                self.fail(where, f"cannot take field '{fname}' of a value of type {t}")
            field = self.structs[t].by_name.get(fname)
            if field is None:
                self.fail(where, f"struct '{t}' has no field '{fname}'")
            links.append(field)
            path.append(field.index)
            t = field.type_name
        return symbol, links, path, t

    def const_field(self, struct_name):
        """The first field, at any depth, that is not 'once changing': its names from the outside in."""
        for f in self.structs[struct_name].fields:
            if not f.mutable:
                return [f.name]
            if f.type_name in self.structs:
                inner = self.const_field(f.type_name)
                if inner is not None:
                    return [f.name] + inner
        return None

    # ---------- collecting: before any body is checked ----------

    def collect_top_level(self, statements):
        for stmt in statements:
            if isinstance(stmt, VarDeclNode):
                self.top_level_vars.add(stmt.name)
            elif isinstance(stmt, ConstDeclNode):
                self.visit(stmt.value)
                self.check_assignable(stmt.value, stmt.type_name, stmt, f"initialise '{stmt.name}'")
                self.check_not_struct(stmt, stmt.name)
                if stmt.name in self.global_consts:
                    self.fail(stmt, f"'{stmt.name}' is already declared in this scope")
                stmt.symbol = Symbol(stmt.name, stmt.type_name, False, "const")
                self.global_consts[stmt.name] = stmt.symbol

    def collect_tasks(self, tasks):
        for task in tasks:
            if task.name in self.structs:
                self.fail(task, f"task '{task.name}' has the name of a struct")
            if task.name in self.tasks:
                self.fail(task, f"task '{task.name}' is already declared")
            seen = set()
            for p in task.params:
                self.check_not_struct(p, p.name)
                if p.name in seen:
                    self.fail(p, f"parameter '{p.name}' is already declared in task '{task.name}'")
                seen.add(p.name)
            self.tasks[task.name] = task

    # ---------- program, structs, tasks and blocks ----------

    def visit_ProgramNode(self, node):
        self.struct_names = {s.name for s in node.structs}
        for struct in node.structs:
            self.visit(struct)
        self.collect_top_level(node.statements)
        self.collect_tasks(node.tasks)
        for task in node.tasks:
            self.visit(task)
        for stmt in node.statements:
            self.visit(stmt)
        self.visit(node.tell)

    def visit_StructNode(self, node):
        if node.name in self.structs:
            self.fail(node, f"struct '{node.name}' is already declared")
        if node.tasks:
            self.fail(node.tasks[0], "this construct is not supported yet")
        fields, seen = [], set()
        for index, f in enumerate(node.fields):
            self.check_not_struct(f, f.name)
            if f.name in seen:
                self.fail(f, f"field '{f.name}' is already declared in struct '{node.name}'")
            seen.add(f.name)
            if f.type_name == node.name:
                self.fail(f, f"struct '{node.name}' cannot contain itself")
            fields.append(FieldInfo(f.name, f.type_name, f.mutable, index))
        node.info = StructInfo(node.name, fields)
        self.structs[node.name] = node.info

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
        symbol, links, path, target = self.resolve_chain(node.names, node.positions)
        full = " of ".join(node.names)
        if not symbol.mutable:
            if len(node.names) == 1:
                self.fail(node, f"cannot assign to '{full}': it is not 'once changing'")
            self.fail(At(node.positions[-1]),
                      f"cannot assign to '{full}': '{symbol.name}' is not 'once changing'")
        for k, field in enumerate(links):       # from the variable outwards
            if not field.mutable:
                where = At(node.positions[len(node.names) - 2 - k])
                self.fail(where, f"cannot assign to '{full}': "
                                 f"field '{field.name}' is not 'once changing'")
        self.visit(node.value)
        self.check_assignable(node.value, target, node, f"assign to '{full}'")
        if target in self.structs:
            const_path = self.const_field(target)
            if const_path is not None:
                shown = " of ".join(reversed(const_path))
                self.fail(node, f"cannot assign to '{full}': field '{shown}' is not 'once changing'")
        node.symbol, node.path, node.target = symbol, path, target

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
        t = self.visit(node.value)
        if t in self.structs:
            self.fail(node.value, f"cannot tell a value of type {t}: an object cannot be told")

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

    def visit_FieldNode(self, node):
        node.symbol, node.links, node.path, node.type = self.resolve_chain(node.names, node.positions)
        return node.type

    def visit_MakeNode(self, node):
        info = self.structs.get(node.struct_name)
        if info is None:
            self.fail(node, f"struct '{node.struct_name}' is not declared")
        if len(node.args) != len(info.fields):
            self.fail(node, f"'{info.name}' needs {len(info.fields)} value(s), got {len(node.args)}")
        for arg, field in zip(node.args, info.fields):
            self.visit(arg)
            self.check_assignable(arg, field.type_name, arg, f"initialise field '{field.name}'")
        node.info = info
        node.type = info.name
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
        for t in (lt, rt):
            if t in self.structs:
                self.fail(node, f"cannot apply '{node.op}' to an object of type {t}")
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