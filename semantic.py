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
        self.mutable = mutable          # True only for "once changing" (and for `this`)
        self.kind = kind                # "const", "var" or "this"
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
        self.methods = {}               # member function name -> TaskNode


class SemanticChecker:
    def __init__(self):
        self.scopes = [{}]              # a stack of frames; the bottom one is the top level
        self.structs = {}               # struct name -> StructInfo
        self.struct_names = set()       # the names of all the structs, known before any is checked
        self.tasks = {}                 # task name -> TaskNode: the signatures
        self.global_consts = {}         # top-level "always" constants, seen by every task
        self.top_level_vars = set()     # names of top-level "once" variables (for a clear error)
        self.current_task = None        # the task or member function whose body is being checked
        self.current_struct = None      # the struct, while the body of a member function is checked
        self.ir_names = set()           # generated names of the member functions, to find a clash
        self.pending = []               # calls of member functions, checked once the flags are known
        self.flags_ready = False        # True when every member function knows if it is mutating

    def check(self, tree):
        self.visit(tree)

    def visit(self, node):
        if not isinstance(node, ExprNode):
            self.at = node      # the statement being checked: where an unexpected error is reported
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            self.fail(node, "this construct is not supported yet")
        return method(node)

    def fail(self, at, msg):
        raise CompileError(f"line {at.line}:{at.col}: {msg}")

    # ---------- symbol table ----------

    def resolve_name(self, name):
        """The frames, then (in a member function) the fields of the struct, then the global
        constants. Returns (symbol, field) or None; `field` is not None for a field of `this`."""
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name], None
        if self.current_struct is not None:
            field = self.current_struct.by_name.get(name)
            if field is not None:
                return self.current_task.this, field
        if self.current_task is not None and name in self.global_consts:
            return self.global_consts[name], None
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

    def resolve_chain(self, names, positions):
        """`x of center of c`: the variable is the last name, the fields follow from the inside out.
        Returns the symbol, the links as (field, position) pairs, the indexes of the gep and the
        type of the end. Inside a member function the last name may be a field of `this`: then
        it is the first link and the symbol is `this`."""
        found = self.resolve_name(names[-1])
        if found is None:
            self.unknown(At(positions[-1]), names[-1])
        symbol, head = found
        links, path = [], []
        t = symbol.type_name
        if head is not None:
            links.append((head, At(positions[-1])))
            path.append(head.index)
            t = head.type_name
        for i in range(len(names) - 2, -1, -1):
            fname, where = names[i], At(positions[i])
            if t not in self.structs:
                self.fail(where, f"cannot take field '{fname}' of a value of type {t}")
            field = self.structs[t].by_name.get(fname)
            if field is None:
                self.fail(where, f"struct '{t}' has no field '{fname}'")
            links.append((field, where))
            path.append(field.index)
            t = field.type_name
        return symbol, links, path, t

    def check_signature(self, task):
        seen = set()
        for p in task.params:
            self.check_not_struct(p, p.name)
            if p.name in seen:
                self.fail(p, f"parameter '{p.name}' is already declared in task '{task.name}'")
            seen.add(p.name)

    def check_call(self, node, callee, what):
        """The number and the types of the arguments: the builder would not notice."""
        if len(node.args) != len(callee.params):
            self.fail(node, f"{what} '{node.name}' takes {len(callee.params)} "
                            f"argument(s), got {len(node.args)}")
        for i, (arg, param) in enumerate(zip(node.args, callee.params), 1):
            self.visit(arg)
            self.check_assignable(arg, param.type_name, arg, f"pass argument {i} of '{node.name}'")

    # ---------- mutating member functions ----------

    def mark_mutating(self):
        """A member function that calls a mutating one on its own object is mutating too.
        Repeat until nothing changes, so that calls in a cycle are decided as well."""
        changed = True
        while changed:
            changed = False
            for info in self.structs.values():
                for task in info.methods.values():
                    if not task.mutating and any(c.mutating for c in task.this_calls):
                        task.mutating = True
                        changed = True

    def check_call_mut(self, node):
        """A mutating member function may be called only through a chain that is mutable at every link."""
        if not node.method.mutating:
            return
        desc = " of ".join(node.obj)
        if not node.symbol.mutable:
            self.fail(node, f"cannot call '{node.name}' on '{desc}': "
                            f"'{node.symbol.name}' is not 'once changing'")
        for field, _ in node.links:
            if not field.mutable:
                self.fail(node, f"cannot call '{node.name}' on '{desc}': "
                                f"field '{field.name}' is not 'once changing'")

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
            self.check_signature(task)
            self.tasks[task.name] = task

    # ---------- program, structs, tasks and blocks ----------

    def visit_ProgramNode(self, node):
        self.struct_names = {s.name for s in node.structs}
        for struct in node.structs:
            self.visit(struct)
        self.collect_top_level(node.statements)
        self.collect_tasks(node.tasks)
        for struct in node.structs:
            for task in struct.tasks:
                self.visit(task)
        for task in node.tasks:
            self.visit(task)
        self.mark_mutating()                    # every body is seen: the flags are final now
        for call in self.pending:
            self.check_call_mut(call)
        self.flags_ready = True
        for stmt in node.statements:
            self.visit(stmt)
        self.visit(node.tell)

    def visit_StructNode(self, node):
        if node.name in self.structs:
            self.fail(node, f"struct '{node.name}' is already declared")
        fields, seen = [], set()
        for index, f in enumerate(node.fields):
            self.check_not_struct(f, f.name)
            if f.name in seen:
                self.fail(f, f"field '{f.name}' is already declared in struct '{node.name}'")
            seen.add(f.name)
            if f.type_name == node.name:
                self.fail(f, f"struct '{node.name}' cannot contain itself")
            fields.append(FieldInfo(f.name, f.type_name, f.mutable, index))
        info = StructInfo(node.name, fields)
        node.info = info
        for task in node.tasks:
            if task.name in info.by_name:
                self.fail(task, f"member function '{task.name}' has the name of a field of '{node.name}'")
            if task.name in info.methods:
                self.fail(task, f"member function '{task.name}' is already declared in '{node.name}'")
            ir_name = f"{node.name}_{task.name}"
            if ir_name in self.ir_names:
                self.fail(task, f"member function '{node.name}.{task.name}' would be "
                                f"'{ir_name}' in the generated code, and that name is taken")
            self.ir_names.add(ir_name)
            self.check_signature(task)
            task.owner = node.name
            task.mutating = False               # decided after all the bodies are checked
            task.this_calls = []                # member functions it calls on its own object
            task.this = Symbol("this", node.name, True, "this")
            info.methods[task.name] = task
        self.structs[node.name] = info

    def visit_TaskNode(self, node):
        saved = (self.scopes, self.current_task, self.current_struct)
        frame = {}
        for p in node.params:
            p.symbol = Symbol(p.name, p.type_name, False, "var")
            frame[p.name] = p.symbol
        self.scopes = [frame]           # the bottom frame holds only the parameters
        self.current_task = node
        self.current_struct = self.structs[node.owner] if node.is_member else None
        self.visit(node.body)           # the body pushes its own frame on top
        self.scopes, self.current_task, self.current_struct = saved

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
        for field, where in links:              # from the variable outwards
            if not field.mutable:
                self.fail(where, f"cannot assign to '{full}': "
                                 f"field '{field.name}' is not 'once changing'")
        self.visit(node.value)
        self.check_assignable(node.value, target, node, f"assign to '{full}'")
        if target in self.structs:
            const_path = self.const_field(target)
            if const_path is not None:
                shown = " of ".join(reversed(const_path))
                self.fail(node, f"cannot assign to '{full}': field '{shown}' is not 'once changing'")
        if symbol.kind == "this":               # a field of its own object: the function is mutating
            self.current_task.mutating = True
        node.symbol, node.path, node.target = symbol, path, target

    def visit_WhenNode(self, node):
        cond_type = self.visit(node.cond)
        if cond_type != "flag":
            self.fail(node, f"the condition of 'when' must be a flag, got {cond_type}")
        self.visit(node.then_block)
        if node.else_block is not None:
            self.visit(node.else_block)

    def visit_WhileNode(self, node):
        cond_type = self.visit(node.cond)
        if cond_type != "flag":
            self.fail(node, f"the condition of 'while' must be a flag, got {cond_type}")
        self.visit(node.body)

    def visit_ForNode(self, node):
        # the bounds are checked before the loop variable exists: they see the outer names
        for bound, word in ((node.start, "from"), (node.end, "to")):
            bound_type = self.visit(bound)
            if bound_type != "int":
                self.fail(bound, f"the bound after '{word}' must be int, got {bound_type}")
        self.check_not_struct(At(node.name_pos), node.name)
        node.symbol = Symbol(node.name, "int", False, "var")
        self.scopes.append({node.name: node.symbol})    # a frame for the loop variable only
        self.visit(node.body)                           # the body pushes its own frame on top
        self.scopes.pop()

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

    def visit_PrintNode(self, node):
        if not isinstance(node.value, StringNode):
            self.visit(node.value)      # an int, a long, a flag or an object; a literal needs no check

    # ---------- expressions: every visit sets node.type and returns it ----------

    def visit_NumberNode(self, node):
        node.type = "int" if node.value <= INT_MAX else "long"
        return node.type

    def visit_BoolNode(self, node):
        node.type = "flag"
        return node.type

    def visit_ReadNode(self, node):
        node.type = "int"
        return node.type

    def visit_VarNode(self, node):
        found = self.resolve_name(node.name)
        if found is None:
            self.unknown(node, node.name)
        symbol, field = found
        node.symbol = symbol
        node.path = [field.index] if field is not None else []
        node.type = field.type_name if field is not None else symbol.type_name
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
        """Inside a member function a name is looked up among the member functions of the same
        struct first, then among the tasks."""
        method = None
        if self.current_struct is not None:
            method = self.current_struct.methods.get(node.name)
        if method is not None:
            self.check_call(node, method, "member function")
            self.current_task.this_calls.append(method)
            node.method, node.task = method, None
            node.type = method.result_type
            return node.type
        task = self.tasks.get(node.name)
        if task is None:
            self.fail(node, f"task '{node.name}' is not declared")
        self.check_call(node, task, "task")
        node.method, node.task = None, task
        node.type = task.result_type
        return node.type

    def visit_MemberCallNode(self, node):
        last = node.obj[-1]
        if self.resolve_name(last) is None and last in self.struct_names:
            self.fail(At(node.obj_positions[-1]),
                      f"cannot call '{node.name}' on the type '{last}': "
                      f"a member function is called on an object")
        symbol, links, path, t = self.resolve_chain(node.obj, node.obj_positions)
        if t not in self.structs:
            self.fail(node, f"cannot call '{node.name}' on a value of type {t}: "
                            f"it has no member functions")
        method = self.structs[t].methods.get(node.name)
        if method is None:
            self.fail(node, f"struct '{t}' has no member function '{node.name}'")
        self.check_call(node, method, "member function")
        node.symbol, node.links, node.path, node.method = symbol, links, path, method
        node.type = method.result_type
        if symbol.kind == "this":               # on its own object or on one of its fields
            self.current_task.this_calls.append(method)
        if self.flags_ready:
            self.check_call_mut(node)
        else:
            self.pending.append(node)
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