"""Telly code generator: builds LLVM IR through the llvmlite builder."""

from llvmlite import ir
import llvmlite.binding as llvm

from lexer import CompileError
from ast_nodes import ConstDeclNode

I1, I8, I32, I64 = ir.IntType(1), ir.IntType(8), ir.IntType(32), ir.IntType(64)
LLVM_TYPES = {"int": I32, "long": I64, "flag": I1}


class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="telly")
        self.module.triple = llvm.get_default_triple()
        self.strings = {}               # text -> global constant
        self.struct_types = {}          # struct name -> the identified type of the module
        self.functions = {}             # task name -> the function of the module
        self.current_task = None        # the task whose body is being generated
        self.n_slots = 0                # allocas already at the start of the entry block
        self.printf = ir.Function(
            self.module,
            ir.FunctionType(I32, [ir.PointerType(I8)], var_arg=True),
            name="printf")              # no blocks: a declaration
        self.function = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.builder = ir.IRBuilder(self.function.append_basic_block("entry"))

    def generate(self, tree):
        self.visit(tree)
        return self.module

    def visit(self, node):
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            raise CompileError(f"line {node.line}:{node.col}: this construct is not supported yet")
        return method(node)

    # ---------- helpers ----------

    def ir_type(self, name):
        if name in LLVM_TYPES:
            return LLVM_TYPES[name]
        return self.struct_types[name]

    def coerce(self, value, have, want):
        if have == "int" and want == "long":
            return self.builder.sext(value, I64)
        return value

    def new_slot(self, llvm_type, name):
        """An alloca at the start of the entry block, whatever block we are in."""
        entry = self.function.entry_basic_block
        saved = self.builder.block
        if self.n_slots < len(entry.instructions):
            self.builder.position_before(entry.instructions[self.n_slots])
        else:
            self.builder.position_at_end(entry)
        ptr = self.builder.alloca(llvm_type, name=name)
        self.n_slots += 1
        self.builder.position_at_end(saved)
        return ptr

    def address_of(self, ptr, path):
        """One gep per link of a chain; the indexes come from the symbol table, never from names."""
        for index in path:
            ptr = self.builder.gep(
                ptr, [ir.Constant(I32, 0), ir.Constant(I32, index)], inbounds=True)
        return ptr

    def str_ptr(self, text):
        """A pointer to a global constant string, created once per text."""
        gv = self.strings.get(text)
        if gv is None:
            data = text.encode("latin-1") + b"\0"
            ty = ir.ArrayType(I8, len(data))
            gv = ir.GlobalVariable(self.module, ty, name=f"str.{len(self.strings)}")
            gv.linkage, gv.global_constant = "private", True
            gv.initializer = ir.Constant(ty, bytearray(data))
            self.strings[text] = gv
        return self.builder.bitcast(gv, ir.PointerType(I8))

    def printf_call(self, fmt, *args):
        self.builder.call(self.printf, [self.str_ptr(fmt)] + list(args))

    def define_constant(self, node):
        node.symbol.const = ir.Constant(LLVM_TYPES[node.type_name], int(node.value.value))

    # ---------- program, structs, tasks and blocks ----------

    def visit_ProgramNode(self, node):
        for struct in node.structs:
            self.visit(struct)
        for stmt in node.statements:
            if isinstance(stmt, ConstDeclNode):
                self.define_constant(stmt)      # a task below may use a constant
        self.declare_tasks(node.tasks)          # every function exists before any body
        for task in node.tasks:
            self.visit(task)
        for stmt in node.statements:
            self.visit(stmt)
        self.visit(node.tell)

    def visit_StructNode(self, node):
        st = self.module.context.get_identified_type(node.name)
        st.set_body(*[self.ir_type(f.type_name) for f in node.fields])
        self.struct_types[node.name] = st

    def declare_tasks(self, tasks):
        for task in tasks:
            fnty = ir.FunctionType(self.ir_type(task.result_type),
                                   [self.ir_type(p.type_name) for p in task.params])
            self.functions[task.name] = ir.Function(self.module, fnty, name=f"fn.{task.name}")

    def visit_TaskNode(self, node):
        saved = (self.builder, self.function, self.n_slots, self.current_task)
        self.function = self.functions[node.name]
        self.current_task = node
        self.n_slots = 0
        self.builder = ir.IRBuilder(self.function.append_basic_block("entry"))
        for arg, p in zip(self.function.args, node.params):
            arg.name = p.name
            p.symbol.ptr = self.new_slot(self.ir_type(p.type_name), p.name)
            self.builder.store(arg, p.symbol.ptr)
        self.visit(node.body)
        self.builder, self.function, self.n_slots, self.current_task = saved

    def visit_BlockNode(self, node):
        for stmt in node.statements:
            self.visit(stmt)

    # ---------- statements ----------

    def visit_ConstDeclNode(self, node):
        self.define_constant(node)

    def visit_VarDeclNode(self, node):
        value = self.coerce(self.visit(node.init), node.init.type, node.type_name)
        node.symbol.ptr = self.new_slot(self.ir_type(node.type_name), node.name)
        self.builder.store(value, node.symbol.ptr)

    def visit_AssignNode(self, node):
        symbol = node.symbol
        value = self.coerce(self.visit(node.value), node.value.type, symbol.type_name)
        self.builder.store(value, symbol.ptr)

    def visit_WhenNode(self, node):
        cond = self.visit(node.cond)
        then_bb = self.function.append_basic_block("then")
        else_bb = None
        if node.else_block is not None:
            else_bb = self.function.append_basic_block("else")
        merge_bb = self.function.append_basic_block("merge")
        self.builder.cbranch(cond, then_bb, else_bb or merge_bb)

        self.builder.position_at_end(then_bb)
        self.visit(node.then_block)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_bb)

        if else_bb is not None:
            self.builder.position_at_end(else_bb)
            self.visit(node.else_block)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_bb)

        self.builder.position_at_end(merge_bb)

    def visit_GiveNode(self, node):
        value = self.visit(node.value)
        value = self.coerce(value, node.value.type, self.current_task.result_type)
        self.builder.ret(value)

    def visit_TellNode(self, node):
        value = self.visit(node.value)
        t = node.value.type
        if t == "flag":
            chosen = self.builder.select(value, self.str_ptr("true"), self.str_ptr("false"))
            self.printf_call("Program exit with result %s\n", chosen)
        else:
            wide = self.coerce(value, t, "long")
            self.printf_call("Program exit with result %lld\n", wide)
        self.builder.ret(ir.Constant(I32, 0))

    # ---------- expressions ----------

    def visit_NumberNode(self, node):
        return ir.Constant(LLVM_TYPES[node.type], node.value)

    def visit_BoolNode(self, node):
        return ir.Constant(I1, int(node.value))

    def visit_VarNode(self, node):
        symbol = node.symbol
        if symbol.kind == "const":
            return symbol.const
        return self.builder.load(symbol.ptr)

    def visit_FieldNode(self, node):
        ptr = self.address_of(node.symbol.ptr, node.path)
        return self.builder.load(ptr)

    def visit_MakeNode(self, node):
        """The whole object as one value: undef, then one insertvalue per field, in order."""
        result = ir.Constant(self.struct_types[node.struct_name], ir.Undefined)
        for arg, field in zip(node.args, node.info.fields):
            value = self.coerce(self.visit(arg), arg.type, field.type_name)
            result = self.builder.insert_value(result, value, field.index)
        return result

    def visit_CallNode(self, node):
        args = [self.coerce(self.visit(a), a.type, p.type_name)
                for a, p in zip(node.args, node.task.params)]
        return self.builder.call(self.functions[node.name], args)

    def visit_BinOpNode(self, node):
        left = self.coerce(self.visit(node.left), node.left.type, node.operand_type)
        right = self.coerce(self.visit(node.right), node.right.type, node.operand_type)
        if node.op == "+":
            return self.builder.add(left, right)
        if node.op == "-":
            return self.builder.sub(left, right)
        if node.op == "*":
            return self.builder.mul(left, right)
        return self.builder.icmp_signed(node.op, left, right)