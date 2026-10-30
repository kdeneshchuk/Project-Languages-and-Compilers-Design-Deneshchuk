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


def optimize(tree):
    """Run the transformations until a round changes nothing."""
    changed = True
    while changed:
        changed = remove_unused_variables(tree)
        changed = remove_unused_tasks(tree) or changed
    return tree

def debug_report(tree):
    names = lambda ts: sorted(t.name for t in ts)
    counts = {}
    count_calls(tree, counts)
    print("calls:", {t.name: counts.get(id(t), 0) for t in tree.tasks})
    print("recursive:", names(t for t in tree.tasks if id(t) in recursive_tasks(tree)))
    print("candidates:", names(inline_candidates(tree)))