"""Telly optimizer: transformations of the checked tree, run behind --optimize."""

from ast_nodes import *


def has_effect(node):
    """May evaluating this expression print or read? A call or read() is never dropped."""
    if isinstance(node, (CallNode, MemberCallNode, ReadNode)):
        return True
    return any(has_effect(child) for child in node.children())


def blocks_of(node):
    """Every list of statements below a node: the program itself and every block."""
    if isinstance(node, ProgramNode):
        yield node.statements
    elif isinstance(node, BlockNode):
        yield node.statements
    for child in node.children():
        yield from blocks_of(child)


class UseCounter:
    """Counts the reads of every declaration, by the identity of its symbol."""
    def __init__(self):
        self.reads = {}                 # id(symbol) -> number of reads
        self.declared = {}              # id(symbol) -> the declaration node

    def read(self, symbol):
        self.reads[id(symbol)] = self.reads.get(id(symbol), 0) + 1

    def visit(self, node):
        if isinstance(node, (VarDeclNode, ConstDeclNode)):
            self.declared[id(node.symbol)] = node
            init = node.init if isinstance(node, VarDeclNode) else node.value
            if has_effect(init):
                self.read(node.symbol)          # kept: its value may print or read
        elif isinstance(node, AssignNode):
            if has_effect(node.value):
                self.read(node.symbol)          # kept together with its declaration
        elif isinstance(node, (VarNode, FieldNode)):
            self.read(node.symbol)
        elif isinstance(node, MemberCallNode):
            self.read(node.symbol)              # the object is read, children() does not show it
        for child in node.children():
            self.visit(child)


def remove_unused_variables(tree):
    """One round. Returns True when something was removed."""
    counter = UseCounter()
    counter.visit(tree)
    dead = {key for key, decl in counter.declared.items()
            if counter.reads.get(key, 0) == 0 and decl.symbol.kind != "this"}
    if not dead:
        return False
    for statements in blocks_of(tree):
        statements[:] = [s for s in statements if not is_dead(s, dead)]
    return True


def is_dead(stmt, dead):
    if isinstance(stmt, (VarDeclNode, ConstDeclNode)):
        return id(stmt.symbol) in dead
    if isinstance(stmt, AssignNode):
        return id(stmt.symbol) in dead
    return False


def count_calls(node, counts):
    """Count the calls of every global task, by the identity of its declaration."""
    if isinstance(node, CallNode) and node.task is not None:
        counts[id(node.task)] = counts.get(id(node.task), 0) + 1
    for child in node.children():
        count_calls(child, counts)


def remove_unused_tasks(tree):
    """One round. Returns True when a task was removed."""
    counts = {}
    count_calls(tree, counts)
    kept = [t for t in tree.tasks if counts.get(id(t), 0) > 0]
    if len(kept) == len(tree.tasks):
        return False
    tree.tasks[:] = kept
    return True

def calls_in(node):
    """Every global task called anywhere below this node, with repeats."""
    found = []
    if isinstance(node, CallNode) and node.task is not None:
        found.append(node.task)
    for child in node.children():
        found.extend(calls_in(child))
    return found


def recursive_tasks(tree):
    """The tasks that can reach themselves through calls, directly or through other tasks."""
    graph = {id(t): {id(c) for c in calls_in(t.body)} for t in tree.tasks}
    recursive = set()
    for t in tree.tasks:
        seen, todo = set(), list(graph[id(t)])
        while todo:
            key = todo.pop()
            if key == id(t):
                recursive.add(id(t))
                break
            if key in seen or key not in graph:
                continue
            seen.add(key)
            todo.extend(graph[key])
    return recursive


def has_early_give(block):
    """A give anywhere except as the last statement of the body itself."""
    for stmt in block.statements[:-1]:
        if contains_give(stmt):
            return True
    return contains_give_inside(block.statements[-1])


def contains_give(node):
    if isinstance(node, GiveNode):
        return True
    return any(contains_give(child) for child in node.children())


def contains_give_inside(last):
    """The last statement is a give: fine. Anything else with a give inside is not simple."""
    return not isinstance(last, GiveNode) and contains_give(last)


def inline_candidates(tree):
    """Tasks called exactly once, not recursive and with a body of a simple shape."""
    counts = {}
    count_calls(tree, counts)
    recursive = recursive_tasks(tree)
    return [t for t in tree.tasks
            if counts.get(id(t), 0) == 1
            and id(t) not in recursive
            and not has_early_give(t.body)]

STATEMENT_FIELDS = {
    # the expressions of a statement that are evaluated once, right where it stands
    VarDeclNode: ("init",), AssignNode: ("value",), TellNode: ("value",),
    GiveNode: ("value",), PrintNode: ("value",), WhenNode: ("cond",),
    ForNode: ("start", "end"),
}                                       # a while is left out: its condition runs on every turn


def find_call(node, task):
    """The one call of this task below a node, or None."""
    if isinstance(node, CallNode) and node.task is task:
        return node
    for child in node.children():
        found = find_call(child, task)
        if found is not None:
            return found
    return None


def effects_outside(node, call):
    """Calls and read() in this expression, not counting the call that is being inlined."""
    if node is call:
        return 0
    own = 1 if isinstance(node, (CallNode, MemberCallNode, ReadNode)) else 0
    return own + sum(effects_outside(child, call) for child in node.children())


def replace_in(node, target, new):
    """The expression with `target` replaced by `new`."""
    if node is target:
        return new
    if isinstance(node, BinOpNode):
        node.left = replace_in(node.left, target, new)
        node.right = replace_in(node.right, target, new)
    elif isinstance(node, (CallNode, MakeNode, MemberCallNode)):
        node.args = [replace_in(a, target, new) for a in node.args]
    return node


def rename_for_inlining(task, moved):
    """Parameters and locals of the inlined body get names the caller cannot have, in every
    declaration and every read of them. A dot cannot stand in a name of the program."""
    names = {id(p.symbol): f"{task.name}.{p.name}" for p in task.params}

    def collect(node):
        if isinstance(node, (VarDeclNode, ConstDeclNode, ForNode)):
            names[id(node.symbol)] = f"{task.name}.{node.name}"
        for child in node.children():
            collect(child)

    def apply(node):
        if isinstance(node, (VarDeclNode, ConstDeclNode, ForNode)):
            node.name = names[id(node.symbol)]
            node.symbol.name = node.name
        elif isinstance(node, (VarNode, FieldNode, AssignNode, MemberCallNode)):
            symbol = getattr(node, "symbol", None)
            if symbol is not None and id(symbol) in names:
                if isinstance(node, VarNode):
                    node.name = names[id(symbol)]
                elif isinstance(node, MemberCallNode):
                    node.obj[-1] = names[id(symbol)]
                else:
                    node.names[-1] = names[id(symbol)]
        for child in node.children():
            apply(child)

    for node in moved:
        collect(node)
    for p in task.params:
        p.symbol.name = names[id(p.symbol)]
    for node in moved:
        apply(node)


def inline_call(statements, index, task):
    """Inline `task` into statements[index], when its call stands in an expression that is
    evaluated once and nothing else in that statement has an effect. True when done."""
    stmt = statements[index]
    fields = STATEMENT_FIELDS.get(type(stmt), ())
    exprs = [getattr(stmt, f) for f in fields]
    call = next((c for c in (find_call(e, task) for e in exprs) if c is not None), None)
    if call is None:
        return False
    if sum(effects_outside(e, call) for e in exprs) > 0:
        return False                                    # moving the body would reorder effects
    body = task.body.statements
    give = body[-1]
    if give.value.type != task.result_type:
        return False                                    # a widening that the generator decides
    prefix = []
    for param, arg in zip(task.params, call.args):
        decl = VarDeclNode(param.line, param.col, f"{task.name}.{param.name}",
                           param.type_name, False, arg)
        decl.symbol = param.symbol                      # the reads in the body already point here
        prefix.append(decl)
    moved = body[:-1] + [give.value]
    rename_for_inlining(task, moved)
    prefix.extend(body[:-1])
    for field, expr in zip(fields, exprs):
        setattr(stmt, field, replace_in(expr, call, give.value))
    statements[index:index + 1] = prefix + [stmt]
    return True

def inline_into_tell(tree, task):
    """The final tell is not in any list of statements: treat it as the last one of the program."""
    holder = tree.statements + [tree.tell]
    if not inline_call(holder, len(holder) - 1, task):
        return False
    tree.statements[:] = holder[:-1]
    tree.tell = holder[-1]
    return True

def inline_one(tree):
    """Inline the first candidate that has a safe place. True when something was inlined."""
    for task in inline_candidates(tree):
        placed = inline_into_tell(tree, task)
        for statements in blocks_of(tree):
            if placed:
                break
            for index in range(len(statements)):
                if inline_call(statements, index, task):
                    placed = True
                    break
        if placed:
            tree.tasks[:] = [t for t in tree.tasks if t is not task]
            return True
    return False

def optimize(tree):
    """Run the transformations until a round changes nothing."""
    changed = True
    while changed:
        changed = remove_unused_variables(tree)
        changed = remove_unused_tasks(tree) or changed
        changed = inline_one(tree) or changed
    return tree