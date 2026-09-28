"""Telly AST: one class per construct of grammar.ebnf."""


class ASTNode:
    def __init__(self, line, col):
        self.line = line
        self.col = col

    def label(self):
        return self.__class__.__name__

    def children(self):
        return []

    def dump(self, indent=0):
        print("  " * indent + self.label())
        for child in self.children():
            child.dump(indent + 1)


class ExprNode(ASTNode):
    pass


class NumberNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value          # int

    def label(self):
        return f"Number {self.value}"


class BoolNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value          # True / False

    def label(self):
        return f"Bool {'true' if self.value else 'false'}"


class VarNode(ExprNode):
    def __init__(self, line, col, name):
        super().__init__(line, col)
        self.name = name

    def label(self):
        return f"Var {self.name}"


class BinOpNode(ExprNode):
    def __init__(self, line, col, op, left, right):
        super().__init__(line, col)
        self.op = op                # "+", "-", "*", "==", "!="
        self.left = left
        self.right = right

    def label(self):
        return f"BinOp {self.op}"

    def children(self):
        return [self.left, self.right]


class StmtNode(ASTNode):
    pass


class ConstDeclNode(StmtNode):
    def __init__(self, line, col, name, type_name, value):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name  # "int", "long", "flag"
        self.value = value          # NumberNode or BoolNode

    def label(self):
        return f"ConstDecl {self.name} {self.type_name}"

    def children(self):
        return [self.value]


class VarDeclNode(StmtNode):
    def __init__(self, line, col, name, type_name, mutable, init):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable      # True for "once changing"
        self.init = init            # any ExprNode

    def label(self):
        return f"VarDecl {self.name} {self.type_name} {'mut' if self.mutable else 'const'}"

    def children(self):
        return [self.init]


class AssignNode(StmtNode):
    def __init__(self, line, col, name, value):
        super().__init__(line, col)
        self.name = name
        self.value = value

    def label(self):
        return f"Assign {self.name}"

    def children(self):
        return [self.value]


class BlockNode(ASTNode):
    """One or more statements. The title ("Then"/"Else") is set by WhenNode."""
    def __init__(self, line, col, statements, title="Block"):
        super().__init__(line, col)
        self.statements = statements
        self.title = title

    def label(self):
        return self.title

    def children(self):
        return self.statements


class WhenNode(StmtNode):
    def __init__(self, line, col, cond, then_block, else_block):
        super().__init__(line, col)
        self.cond = cond
        self.then_block = then_block
        self.else_block = else_block    # None if there is no "otherwise"
        then_block.title = "Then"
        if else_block is not None:
            else_block.title = "Else"

    def label(self):
        return "When"

    def children(self):
        kids = [self.cond, self.then_block]
        if self.else_block is not None:
            kids.append(self.else_block)
        return kids


class TellNode(ASTNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def label(self):
        return "Tell"

    def children(self):
        return [self.value]


class ProgramNode(ASTNode):
    def __init__(self, line, col, statements, tell):
        super().__init__(line, col)
        self.statements = statements
        self.tell = tell

    def label(self):
        return "Program"

    def children(self):
        return self.statements + [self.tell]
