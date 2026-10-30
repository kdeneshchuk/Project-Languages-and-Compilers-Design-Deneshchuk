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


def optimize(tree):
    """Run the transformations until a round changes nothing."""
    changed = True
    while changed:
        changed = remove_unused_variables(tree)
    return tree