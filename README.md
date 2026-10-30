# Telly

Telly is a small programming language that reads like a story. A program is a
sequence of sentences; every sentence ends with a full stop. Words carry the
meaning instead of symbols: a variable *was* something once, and later it
*became* something else.

This repository is stage 3 of the CS400 course project. Stage 1 gave the
language a lexer, a parser and an AST. Stage 2 made it run: tasks
(functions), structs with fields and member functions, `read` and `print`, a
semantic pass and code generation to LLVM IR through `llvmlite`. Stage 3 adds
one feature of its own: loops, `while` and `for` over an integer range (see
[Loops](#loops)).

```
always int LEGAL_AGE is 18.
once int age was 19.
once changing flag allowed was 👎.

when age 🟰 LEGAL_AGE:
    allowed became 👍.
otherwise:
    allowed became 👎.
end.

tell allowed.
```

`age` is 19 and `LEGAL_AGE` is 18, so the comparison is false and the
program reports `Program exit with result false`.

## The language

### Types

Three built-in types: `int` (32-bit), `long` (64-bit) and `flag` (boolean).
A struct declared in the program is a type too. A type name is `int`, `long`,
`flag` or the name of a struct declared above.

```
once int small was 42.
once long big was 3000000000.
once flag ready was yes.
```

### Three kinds of names

| Kind | Written as | Right-hand side |
|---|---|---|
| constant | `always` … `is` | a literal only |
| immutable variable | `once` … `was` | any expression |
| mutable variable | `once changing` … `was` | any expression |

```
always int LIMIT is 100.
once int age was 19.
once changing int score was 0.
```

The verbs are the tense of the sentence: a constant *is*, a variable *was*
set once, and only a `changing` one later *became* something else. A
constant is `int`, `long` or `flag`, never an object.

### Assignment

```
score became score + 10.
```

### Expressions

Arithmetic uses `+`, `-` and `*`. Multiplication binds tighter, and
operators of equal precedence group from left to right. There is no
division and no grouping parentheses.

```
once int a was 2 + 3 * 4.
once int b was 10 - 3 - 2.
```

Here `a` is 14 and `b` is 5.

A comparison gives a `flag`. It binds weaker than arithmetic, and there is at
most one per expression.

```
once flag c was a + 1 equals b * 3.
```

### Comparisons and truth values, in words or in emoji

Each of these has two spellings, and they mean exactly the same thing:

| Meaning | Word | Emoji |
|---|---|---|
| equal | `equals` | 🟰 |
| not equal | `differs` | 🚫 |
| true | `yes` | 👍 |
| false | `no` | 👎 |

```
once flag p was age equals 19.
once flag q was age 🚫 20.
once flag r was 👍.
```

### Conditions

`when` takes a condition, a colon and a block; `otherwise` and its block are
optional; `end.` closes the sentence. Each block holds at least one statement,
and conditions can be nested, up to 100 levels deep (the limit is shared
with loops, see Loops).

```
when score 🟰 100:
    ready became yes.
    score became 0.
otherwise:
    ready became no.
end.
```

### Loops

`while` repeats a block as long as a condition is true. `for` repeats a block
once for every integer from a first value to a last one.

```
while i differs 6:
    ...
end.

for n from 1 to 5:
    ...
end.
```

The rules:

1. The condition of `while` is a `flag`. It is tested before every turn, so a
   `while` whose condition is false at the start does not run at all, and a
   `read()` in the condition is evaluated on every turn.
2. `for n from A to B` takes two `int` expressions. Both are evaluated once,
   from left to right, before the first turn, and they see the names declared
   outside the loop. Changing a variable inside the body does not change the
   bounds.
3. The bounds are inclusive: `for n from 1 to 5` runs for 1, 2, 3, 4 and 5. When
   `A` is greater than `B` the body does not run at all. The loop also works
   with `to 2147483647`: it stops when the variable is equal to `B`, before an
   increment that would overflow.
4. The variable of a `for` is an `int`, is not `once changing`, and is visible
   only in the body of the loop. It cannot be assigned, and after `end.` the name
   is free again. The bounds are checked before the variable exists, so
   `for n from n to 3` reads an `n` declared outside. A declaration in the body
   may reuse the name and hides the loop variable.
5. A body holds at least one statement and ends with `end.`. A variable
   declared in the body belongs to that body: it is created again, with its
   initial value, on every turn.
6. A loop is a statement. It stands wherever a statement can: at the top level,
   in a task or a member function, in the block of a `when`, in another loop.
   `give` inside a loop of a task leaves the task at once. `tell` stays the
   last statement of the program and cannot stand inside a loop.
7. `when`, `while` and `for` share one limit: together they nest at most 100
   levels deep.
8. `while`, `for`, `from` and `to` are reserved words.

Example 1: `while` with a counter. It prints 15 and reports 6.

```
once changing int i was 1.
once changing int sum was 0.
while i differs 6:
    sum became sum + i.
    i became i + 1.
end.
print(sum).
tell i.
```

Example 2: a loop inside a loop. The inner loop declares a variable, and the
program reports 36, the sum of `a * b` for all pairs from 1 to 3.

```
once changing int total was 0.
for a from 1 to 3:
    for b from 1 to 3:
        once int p was a * b.
        total became total + p.
    end.
end.
tell total.
```

### Reporting the result and ending the program

`tell` names the value the program reports at the end. It takes a number, a
truth value, a name, a field chain, a call, a member call or `read()`, never
an operation or an object, and it is the last statement of every program,
never inside a block or a task. The compiled program writes
`Program exit with result N`, where `N` is the value; a `flag` is written as
`true` or `false`.

```
tell score.
```

### Reserved words

`always`, `once`, `changing`, `is`, `was`, `became`, `when`, `otherwise`,
`end`, `tell`, `int`, `long`, `flag`, `equals`, `differs`, `yes`, `no`,
`struct`, `task`, `giving`, `give`, `of`, `make`, `print`, `read`,
`while`, `for`, `from`, `to`.

Names are letters, digits and `_`, and may not start with a digit. Keywords
are case-sensitive, so `Tell` and `YES` are ordinary names.

### Not part of the language

Division, `<`, `>`, a lone `=` or `!`, `{`, `}`, `;`, a sign in front of a
number (write `0 - 5`), two comparisons in one expression, anything after
`tell`, comments, grouping parentheses (`(1 + 2)`), a task or a struct
inside a task, two tasks with one name, `break`, a step other than 1 in a
`for`, and a loop variable of a type other than `int`. Parentheses exist only in a call,
in `make`, in `read()` and in `print(...)`. Each of the above is a
compilation error.

### Program order

```
program ::= { struct_decl } { task_decl } { statement } tell_stmt
```

Structs come first, then tasks, then statements, then the final `tell`. A
struct after a task or a statement, or a task after a statement, is an error
at that line.

## Types and expressions: the rules

1. A decimal number has the narrowest type it fits: `int` up to
   2147483647, then `long` up to 9223372036854775807. A bigger number is an
   error.
2. `+`, `-` and `*` take two numbers (`int` or `long`) and give the wider
   type: `int + long` is `long`. A `flag` or an object operand is an error.
3. `equals` and `differs` take two numbers of any width, or two `flag`s, and
   give a `flag`. A `flag` against a number, or an object operand, is an
   error.
4. An `int` widens into `long` where a `long` is expected: an initialiser, an
   assignment, a field, an argument, a `give`. Nothing else converts: a
   `long` never narrows, and a `flag` never meets a number.
5. The condition of `when` is a `flag`.
6. Overflow is checked by type, not by value. A number written next to its
   type must fit it (`once int z was 2147483648.` is an error). A `long`
   expression cannot go into an `int` (`once int x was 5 + 3000000000.` and
   `x became 3000000000.` are errors), but two `int` numbers whose sum does
   not fit are not detected: `2000000000 + 2000000000` is an `int`.

## Scopes

1. Every block of a `when` is a scope of its own: the block after `:` and
   the block after `otherwise:` are two scopes. A task body is a scope too.
   The body of a loop is a scope too, and the variable of a `for` lives in a
   scope of its own around the body.
2. A declaration goes into the innermost scope. The same name cannot be
   declared twice in one scope, the body of a task included.
3. An inner scope may declare a name that an outer one has, with any type;
   it hides the outer one until the end of the block (shadowing). A task
   body may declare a name of one of its parameters.
4. A name is looked up from the innermost scope outwards and takes the first
   hit. At the top level a name must be declared before its first use. A name
   that is in no scope, including one whose block has ended, is an error.
   The one exception is the global constants: an `always` declared at the
   top level, outside any `when`, is visible in every task and member
   function, wherever it stands, even above the constant (see Tasks,
   rule 3). An `always` inside a `when` or a task is an ordinary local name.
5. A variable, a parameter or a field may have the name of a task, because
   a call is told from a name by its `(`. It may not have the name of a
   struct.

## Tasks

A task is a function. The rules come first; the syntax follows.

1. A task has a name, parameters and a result type. A parameter type and
   the result type are `int`, `long`, `flag` or the name of a struct
   declared above. Parameter names are unique within a task.
2. A parameter is a constant copy of its argument. It cannot be
   assigned, even if the caller's variable is `once changing`.
3. A name in a task body is looked up among the parameters and the
   task's own variables (the innermost `when` block first, then outwards),
   then among the global `always` constants. The `once` variables of the
   top level are not visible. A global constant is visible in every task,
   also in one declared above the constant. A parameter or a local
   variable named like a global constant hides it.
   A local variable may have the name of a parameter: it hides the
   parameter from its declaration to the end of its block. The same name
   cannot be declared twice in one block, the block of a task body
   included. A body also sees all the tasks of the program (to call them)
   and all the structs (as types).
4. A task leaves with `give`. The last statement of the body is `give`;
   `give` may also stand inside `when` to leave early. In every block
   `give` is the last statement: nothing follows it in the same block. The
   value must have the result type. An `int` may be given where `long` is
   expected; nothing else converts.
5. A call has the result type of its task. It stands wherever a factor
   can: in an expression, as an argument of another call, after `tell`,
   `give` and inside `print`. A call alone is not a statement.
6. A call has as many arguments as the task has parameters, and each
   argument has the type of its parameter. An `int` argument may go into
   a `long` parameter.
7. All signatures are collected before any body is checked, so a task may
   call itself and any task declared below it.
8. A task name is unique, is not the name of a struct, and is not `read`
   or `print`.
9. Tasks come after the structs and before the statements. `give` stands
   only inside a task.

```
task add(int a, int b) giving int:
    once int r was a + b.
    give r.
end.

once int c was add(5, add(3, 2)).
tell c.
```

The program reports `Program exit with result 10`.

## Structs

1. A struct has a name and at least one field. Its name is unique, is not
   the name of a task, and is not `read` or `print`.
2. A field is written `once type name.` and is constant, or
   `once changing type name.` and is mutable. Field names are unique within
   a struct. A field type is `int`, `long`, `flag` or a struct declared
   above; a struct cannot contain itself. A type name that is none of
   these is a compilation error.
3. An object is created with `make T(v1, ..., vn)`. `T` must be a struct,
   and there is exactly one value for every field, in the order of the
   fields. A value has the type of its field; an `int` may go into a
   `long` field. A field of a struct type takes an object: a variable, a
   call that returns one, or another `make`.
4. An object variable is declared like any variable:
   `once changing T p was make T(...).`. The right side may be any
   expression of type `T`, and then the variable is a copy. Objects are
   values: a copy can be changed without touching the original. A task gets a
   constant copy of its argument (Tasks, rule 2); to change an object inside a
   task, copy it into a `once changing` variable first.
5. A field is read with `of`, from the inside out: `x of center of c` is
   the field `x` of the field `center` of the variable `c`. Every link of
   the chain must exist. A read is allowed on any object.
6. A field is written with `became` through the same chain, and only if
   every link is mutable: the variable is `once changing` and every field
   on the way is `once changing`. A single constant link makes the whole
   write an error, whichever other links are mutable.
7. A value of a struct type may be assigned to a variable (`p became q.`)
   or to a field (`center of c became q.`) when the whole chain is mutable,
   the value has the same struct type, and every field of that struct, at
   every depth, is `once changing`.
8. An operator, `when` and `tell` do not take an object: an object cannot
   be added, compared or told. It can be passed to a task, given, and
   printed.

```
struct Point:
    once changing int x.
    once changing int y.
end.

struct Circle:
    once Point center.
    once changing int radius.
end.

once changing Circle c was make Circle(make Point(10, 20), 5).
radius of c became 7.
once int cx was x of center of c.
tell cx.
```

The program reports `Program exit with result 10`.

## Member functions

1. A task declared inside a struct, after its fields, is a member
   function. A task before the first field is an error at that `task`, and
   a field after a task is an error at that field. A field and a member
   function of one struct cannot share a name, and neither can two member
   functions. A member function is not called `read` or `print`.
2. A member function is called on an object: `name(args) of object`. The
   object is a variable or a chain: `d2() of p`, `d2() of center of c`. It
   must have a struct type that declares `name`. A call on a type
   (`d2() of Point`), on an `int` or on an unknown member is an error. The
   number and the types of the arguments follow the rules of tasks. A call
   ends the chain: nothing follows it.
3. A name inside a member function is looked up among the parameters and
   locals (the innermost `when` block first, then outwards), then among the
   fields of the struct, then among the global `always` constants. A
   parameter or a local named like a field hides the field, and a field
   named like a global constant hides the constant. The `once` variables of
   the top level are not visible.
4. A call `f(...)` inside a member function looks among the member
   functions of the same struct first, then among the tasks. A member
   function hides a task of the same name, and `d2()` inside `Point` is
   called on the same object.
5. A field that is not `once changing` cannot be assigned, also inside a
   member function. A parameter cannot be assigned either.
6. A member function is mutating if it assigns a field of its object, or
   calls a mutating member function on its object or on a field of it. A
   mutating function may be called only through a chain where every link is
   `once changing`: the variable and each field on the way. A non-mutating
   one may be called on anything. A local variable named like a field does
   not make a function mutating. A parameter is constant, so a task cannot
   call a mutating member function on its parameter. Member functions may
   call each other in a cycle, so mutating functions are decided after all
   bodies are checked.
7. `give` in a member function follows the rules of tasks: the last
   statement of the body, with the result type.
8. Two member functions whose names in the generated code would be equal
   (`c` of `A_B` and `B_c` of `A`, both `A_B_c`) are an error at the
   second one.

```
struct Point:
    once changing int x.
    once changing int y.
    task d2() giving int:
        once int r was x * x + y * y.
        give r.
    end.
    task shift(int dx) giving int:
        x became x + dx.
        give x.
    end.
end.

once changing Point p was make Point(3, 4).
once int d was d2() of p.
once int n was shift(2) of p.
tell n.
```

`d` is 25, `shift` moves `p.x` to 5, and the program reports
`Program exit with result 5`.

## read and print

1. `read()` reads one integer from the standard input. Its type is `int`
   (and an `int` widens into `long` as usual). It takes no arguments and
   stands wherever a factor can. An empty input gives 0. Operands, call
   arguments and `make` values are evaluated from left to right, so
   `make Point(read(), read())` reads `x` first.
2. `read` and `print` are reserved: a variable, task, parameter, field or
   member function cannot have these names.
3. `print(arg).` is a statement. It stands wherever a statement can: at
   the top level, in a task, a member function and a `when` block. It has no
   value, so `once int x was print(1).` is an error at `print`. It has
   exactly one argument.
4. The argument is one of:
   - an `int` or `long` value: the number, as `-9` or `6000000000`;
   - a `flag`: the word `true` or `false`, never `yes`, `no`, `1` or `0`;
   - a string literal: its text as written;
   - an object (a variable, a field chain, a call that returns one, or
     `make`): the name of the struct and its fields in declaration order,
     `Point{x: 3, y: 4}`; a field that is an object is printed the same way
     one level down, `Circle{center: Point{x: 3, y: 4}, radius: 2}`, and a
     `flag` field is `true` or `false`.
5. A string literal is `"`, any bytes except `"` and a newline, then `"`.
   There are no escape sequences: `\n` is two characters, and a `%` stays a
   `%`. A literal stands only as the argument of `print`, and one not closed
   on its line is an error at its opening `"`.
6. `print` puts exactly one newline after everything it prints, after the
   closing `}` of an object too. The output of `print` comes before the
   last line `Program exit with result N`, which the program writes at
   `tell`.

With the struct `Point` and its member function `d2` of the previous
section:

```
once changing Point p was make Point(read(), read()).
print("p and its square:").
print(p).
print(d2() of p).
tell x of p.
```

With `3 4` on the standard input the program prints `p and its square:`,
`Point{x: 3, y: 4}`, `25` and `Program exit with result 3`.

## Code generation

The IR is built only through the `llvmlite.ir` builder; the only IR text the
compiler writes is `str(module)`.

- Every `when` becomes `then`, `else` (when there is one) and `merge` basic
  blocks and one conditional branch; each block ends with exactly one
  terminator. Every `alloca` goes into the entry block of its function.
- A struct is a named type, `%"Point" = type {i32, i32}`, an object is an
  `alloca` of it, and a field is reached with `getelementptr` by the index
  the semantic pass found, one `gep` per link of a chain. The generator
  never looks a field up by name.
- Every task is a function of the module named `fn.<name>`, so a task
  called `main` or `printf` does not clash with the runtime. All tasks are
  declared before any body is generated. A parameter is stored into a slot
  in the task's own entry block, `give` becomes `ret`, a call becomes
  `call`. Objects travel by value into and out of tasks.
- A member function is a function named after the struct and the task,
  `Point_shift`. Its first parameter is a pointer to the object, and a call
  passes the address of the object, so `shift` changes the caller's object.
  A field in the body is a `gep` on that pointer.
- Global `always` constants are not stored anywhere: a use is the constant
  itself.
- `printf` and `scanf` are declared in the module, as functions with a type
  and no body. The formats are global constants: `%d` for `int`, `%lld` for
  `long`, `%s` with a choice between the strings `true` and `false` for
  `flag`. At `tell`, an `int` is widened to 64 bits and written with `%lld`
  like a `long`. An object is printed by walking the field table of its
  struct, a `gep`, a `load` and a `printf` per field, so a new struct is
  printed with no new compiler code. The final `Program exit with result N` 
  is written by `main` at `tell`.

### Loops in the IR

A `while` becomes three basic blocks: `while.cond`, `while.body` and
`while.end`. This is the IR of `while i differs 4:` with the body
`i became i + 1.`:

```
entry:
  %"i" = alloca i32
  store i32 1, i32* %"i"
  br label %"while.cond"
while.cond:
  %".4" = load i32, i32* %"i"
  %".5" = icmp ne i32 %".4", 4
  br i1 %".5", label %"while.body", label %"while.end"
while.body:
  %".7" = load i32, i32* %"i"
  %".8" = add i32 %".7", 1
  store i32 %".8", i32* %"i"
  br label %"while.cond"
while.end:
```

`while.cond` loads `i`, compares it with 4 using `icmp ne` and branches to
`while.body` or `while.end`, so the condition is tested again on every turn.
`while.body` loads `i`, adds 1 and stores it back, and its last instruction,
`br label %"while.cond"`, is the back edge: the only jump that goes to a block
that has already run. The slot of `i` is allocated once in `entry`, outside the
loop, and `while.end` is where the statements after `end.` go on.

A `for` has the blocks `for.body`, `for.step` and `for.end`. Both bounds are
computed once before the loop, and a first comparison skips the body when the
range is empty. At the end of the body the variable is compared with the last
value *before* it is incremented, so a loop that ends at 2147483647 does not
overflow; `for.step` adds 1 and branches back to `for.body`.

## Setup

Python 3.10 or newer, the `llvmlite` package, and the LLVM tools `lli`, `llc`
and `clang` to run the result. Tested with Python 3.12.3, llvmlite 0.49.0 and
LLVM 18.1.3 on Ubuntu.

On Ubuntu or Debian:

```bash
sudo apt install python3 python3-venv llvm clang
python3 -m venv .venv
source .venv/bin/activate
pip install llvmlite
```

On macOS, `clang` comes with the Xcode command line tools, and `lli` and
`llc` with Homebrew's LLVM:

```bash
xcode-select --install
brew install llvm
export PATH="$(brew --prefix llvm)/bin:$PATH"
python3 -m venv .venv
source .venv/bin/activate
pip install llvmlite
```

## Running the compiler

```bash
source .venv/bin/activate                  # once per terminal
python3 compiler.py input.txt output.ll    # compile
python3 compiler.py --ast input.txt        # print the AST, write nothing
python3 compiler.py --tokens input.txt     # print the token stream
lli output.ll < input.in                   # run, a program that calls read()
llc -filetype=obj -relocation-model=pic output.ll -o output.o
clang -fPIE output.o -o program && ./program
```

`--ast` prints the tree after parsing, so it reports lexical and syntax
errors but does not run the semantic pass. The semantic pass runs when a
program is compiled to `output.ll`.

On any error, lexical, syntax or semantic, the compiler prints one line to
stderr, exits with a non-zero code and writes no output file:

```
$ python3 compiler.py tests/err/missing_end.txt out.ll
compilation error: line 3:1: expected 'end', got 'tell'
```

Exit codes: `0` success, `1` the program is not valid Telly, `2` the compiler
was called wrongly or the file could not be read.

## Running the tests

```bash
python3 run_tests.py
```

A test is a program `NAME.txt` with the files next to it that say what to
check:

- `tests/ok/NAME.ast`: the AST dump of the program.
- `tests/ok/NAME.expected`: the program is compiled to `.ll`, built and run
  (with `lli`, or with `llc` and `clang` if `lli` is missing), and its whole
  standard output is compared with this file. This is an end-to-end test.
- `tests/ok/NAME.in`: the standard input of the program. The `.expected` file
  holds only what the program prints, since the input is not echoed.
- `tests/err/NAME.expected`: the error line the compiler must print. The
  runner also checks that the exit code is 1 and that no `.ll` is written.

Compiled files go to a temporary directory, never into `tests/`. A valid
program has an `.ast`, an `.expected`, or both. Four programs from stage 1
(`expr_compare_arith`, `nesting_at_limit`, `stage2_overflow_not_checked`,
`stage2_semantics_not_checked`) are correct for the parser but not for the
semantic pass, so they only have an `.ast` and are not compiled. The runner
prints one line per test and a summary, says which tests failed and exits
with a non-zero code if any did.

Every rule in this README is covered by one program that follows it and one
that breaks it, and the tests are named after the rule they cover.
The tests of the loops are named `loop_*`: `tests/ok/loop_*` run loops end to
end, including the edge cases (an empty range, a bound of 2147483647, nested
loops, a loop inside a task and a member function), and `tests/err/loop_*`
break each rule of Loops.

## VS Code extension (optional)

`vscode-telly/` supports files with the extension `.telly`, or any file whose
language mode is set to Telly.

- **Highlighting** of keywords, types, strings, names of structs and tasks.
- **Completions** for 👍 👎 🟰 🚫 and **snippets** for `when`, `struct`,
  `task` and `print`.
- **Diagnostics from the compiler.** While you type, the extension compiles
  the text of the editor with `compiler.py` into a temporary directory and
  underlines the place named in the error line
  `compilation error: line L:C: message`; the message shows on hover. The
  extension has no checks of its own: the compiler is the only judge, so the
  editor and the terminal always agree. The compiler counts columns in bytes
  and VS Code in UTF-16 units, so `errors.js` converts them (an emoji is four
  bytes and two units).

Settings: `telly.diagnostics` (on or off), `telly.pythonPath` (a Python with
`llvmlite`, e.g. `.venv/bin/python3`) and `telly.compilerPath` (empty means
`compiler.py` of the open folder).

To install, copy the folder to `~/.vscode/extensions/kdeneshchuk.telly-0.1.0`
(`~/.vscode-server/extensions/` when VS Code is connected over SSH) and
reload the window.

## How it is built

| File | What it does |
|---|---|
| `grammar.ebnf` | the grammar, the lexical rules and the rules EBNF cannot express |
| `lexer.py` | a state machine over bytes: identifiers, numbers, strings, emoji, symbols |
| `ast_nodes.py` | the node classes and the `--ast` dump |
| `parser.py` | recursive descent, one function per grammar rule |
| `semantic.py` | the semantic pass: symbol table for variables, tasks and structs |
| `codegen.py` | code generation through the `llvmlite` builder |
| `compiler.py` | the command line |
| `run_tests.py` | the test runner |
| `vscode-telly/` | an optional [VS Code extension](#vs-code-extension-optional): highlighting, snippets, 👍 👎 🟰 🚫 completions and the compiler's errors under the code |

The lexer reads bytes, not characters. An emoji is four bytes, recognised as
a byte sequence exactly like a keyword written in letters, so a column after
an emoji advances by four. A tab counts as one column. Carriage returns are
ignored, so files with Windows line endings work.