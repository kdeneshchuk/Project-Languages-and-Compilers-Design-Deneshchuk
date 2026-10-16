"""Telly AST: one class per construct of grammar.ebnf."""


class ASTNode:
    def __init__(self, line, col):
        self.line = line
        self.col = col

    def label(self):
        return self.__class__.__name__

    def children(self):
        return []

    def dump_lines(self, indent=0, out=None):
        out = out if out is not None else []
        out.append("  " * indent + self.label())
        for child in self.children():
            child.dump_lines(indent + 1, out)
        return out

    def dump(self, indent=0):
        print("\n".join(self.dump_lines(indent)))


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


class StringNode(ExprNode):
    def __init__(self, line, col, text):
        super().__init__(line, col)
        self.text = text            # bytes of the literal, decoded as latin-1

    def label(self):
        shown = self.text.encode("latin-1").decode("utf-8", "replace")
        return f'String "{shown}"'


class VarNode(ExprNode):
    def __init__(self, line, col, name):
        super().__init__(line, col)
        self.name = name

    def label(self):
        return f"Var {self.name}"


class FieldNode(ExprNode):
    """A chain of two or more names: x of center of c."""
    def __init__(self, line, col, names):
        super().__init__(line, col)
        self.names = names          # source order: the variable is the last

    def label(self):
        return "Field " + " of ".join(self.names)


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


class ReadNode(ExprNode):
    def label(self):
        return "Read"


class MakeNode(ExprNode):
    def __init__(self, line, col, struct_name, args):
        super().__init__(line, col)
        self.struct_name = struct_name
        self.args = args            # one value per field

    def label(self):
        return f"Make {self.struct_name}"

    def children(self):
        return self.args


class CallNode(ExprNode):
    def __init__(self, line, col, name, args):
        super().__init__(line, col)
        self.name = name
        self.args = args

    def label(self):
        return f"Call {self.name}"

    def children(self):
        return self.args


class MemberCallNode(ExprNode):
    """A call of a member function on an object: shift(2) of center of c."""
    def __init__(self, line, col, name, args, obj):
        super().__init__(line, col)
        self.name = name
        self.args = args
        self.obj = obj              # names of the object chain, source order

    def label(self):
        return f"MemberCall {self.name} of " + " of ".join(self.obj)

    def children(self):
        return self.args


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
        self.type_name = type_name  # a built-in type or a struct name
        self.mutable = mutable      # True for "once changing"
        self.init = init            # any ExprNode

    def label(self):
        return f"VarDecl {self.name} {self.type_name} {'mut' if self.mutable else 'const'}"

    def children(self):
        return [self.init]


class AssignNode(StmtNode):
    def __init__(self, line, col, names, value):
        super().__init__(line, col)
        self.names = names          # ["x"] or ["x", "center", "c"]
        self.value = value

    def label(self):
        return "Assign " + " of ".join(self.names)

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


class PrintNode(StmtNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value          # StringNode or any ExprNode

    def label(self):
        return "Print"

    def children(self):
        return [self.value]


class GiveNode(StmtNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def label(self):
        return "Give"

    def children(self):
        return [self.value]


class TellNode(StmtNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def label(self):
        return "Tell"

    def children(self):
        return [self.value]


class FieldDeclNode(ASTNode):
    def __init__(self, line, col, name, type_name, mutable):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable

    def label(self):
        return f"Member {self.name} {self.type_name} {'mut' if self.mutable else 'const'}"


class ParamNode(ASTNode):
    def __init__(self, line, col, name, type_name):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name

    def label(self):
        return f"Param {self.name} {self.type_name}"


class TaskNode(ASTNode):
    def __init__(self, line, col, name, params, result_type, body, is_member=False):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.result_type = result_type
        self.body = body
        self.is_member = is_member  # True for a task declared inside a struct

    def label(self):
        kind = "MemberTask" if self.is_member else "Task"
        return f"{kind} {self.name} -> {self.result_type}"

    def children(self):
        return self.params + [self.body]


class StructNode(ASTNode):
    def __init__(self, line, col, name, fields, tasks):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.tasks = tasks          # the member functions

    def label(self):
        return f"Struct {self.name}"

    def children(self):
        return self.fields + self.tasks


class ProgramNode(ASTNode):
    def __init__(self, line, col, statements, tell, structs=(), tasks=()):
        super().__init__(line, col)
        self.structs = list(structs)
        self.tasks = list(tasks)
        self.statements = statements
        self.tell = tell

    def label(self):
        return "Program"

    def children(self):
        return self.structs + self.tasks + self.statements + [self.tell]