# Telly

Telly is a small programming language that reads like a story. A program is a
sequence of sentences; every sentence ends with a full stop. Words carry the
meaning instead of symbols: a variable *was* something once, and later it
*became* something else.

This repository is stage 1 of the CS400 course project: the language design,
a hand-written lexer, a recursive-descent parser and the AST it builds.

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

## The language

### Types

Three types: `int` (32-bit), `long` (64-bit) and `flag` (boolean).

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
set once, and only a `changing` one later *became* something else.

### Assignment

```
score became score + 10.
```

### Expressions

Arithmetic uses `+`, `-` and `*`. Multiplication binds tighter, and
operators of equal precedence group from left to right. There are no
parentheses and no division.

```
once int a was 2 + 3 * 4.      a is 14
once int b was 10 - 3 - 2.     b is 5
```

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
and conditions can be nested.

```
when score 🟰 100:
    ready became yes.
    score became 0.
otherwise:
    ready became no.
end.
```

### Printing and ending the program

`tell` prints one value and ends the program. It takes a number, a truth
value or a name, never an operation, and it is the last statement of every
program.

```
tell score.
```

### Overflow of number literals

A number written next to its type must fit in it:

```
once int x was 2147483647.       accepted
once int y was 2147483648.       compilation error
once long z was 9223372036854775808.    compilation error, too big for long
```

### Reserved words

`always`, `once`, `changing`, `is`, `was`, `became`, `when`, `otherwise`,
`end`, `tell`, `int`, `long`, `flag`, `equals`, `differs`, `yes`, `no`.

Names are letters, digits and `_`, and may not start with a digit. Keywords
are case-sensitive, so `Tell` and `YES` are ordinary names.

### Not part of the language

Parentheses, division, `<`, `>`, a lone `=` or `!`, `{`, `}`, `;`, a sign in
front of a number (write `0 - 5`), two comparisons in one expression,
anything after `tell`, and comments. Each of these is a compilation error.

## Running the compiler

Python 3.8 or newer is the only requirement. There is nothing to install and
nothing to build.

```bash
python3 compiler.py --ast examples/age.telly    # print the AST
python3 compiler.py examples/age.telly          # parse only, print nothing
python3 compiler.py --tokens examples/age.telly # print the token stream
```

`--tokens` is a debugging aid: it shows what the lexer produced, one token
per line, as `line:column kind 'text'`.

On an error the compiler prints one line to stderr and exits with a non-zero
code, and prints nothing to stdout:

```
$ python3 compiler.py --ast tests/err/missing_end.txt
compilation error: line 3:1: expected 'end', got 'tell'
```

Exit codes: `0` success, `1` the program is not valid Telly, `2` the compiler
was called wrongly or the file could not be read.

## Running the tests

```bash
python3 run_tests.py
```

The runner compiles every program in `tests/ok` and compares the AST dump
with the `.ast` file next to it, then compiles every program in `tests/err`
and compares the error line with the `.expected` file. It prints one line per
test and a summary, and exits with a non-zero code if anything failed.

```
PASS  ok/if_else_nested
FAIL  err/missing_end

93 of 94 tests passed
failed: err/missing_end
```

There are 38 valid and 56 invalid programs. Every feature of the language is
covered from both sides.

## How it is built

| File | What it does |
|---|---|
| `grammar.ebnf` | the grammar, and the rules EBNF cannot express |
| `lexer.py` | a state machine over bytes: `START`, `IDENT`, `NUMBER`, `EMOJI` |
| `ast_nodes.py` | the node classes and the `--ast` dump |
| `parser.py` | recursive descent, one function per grammar rule |
| `compiler.py` | the command line |
| `run_tests.py` | the test runner |
| `vscode-telly/` | an optional [VS Code extension](vscode-telly/) that highlights Telly and offers 👍 👎 🟰 🚫 as completions |

The lexer reads bytes, not characters. An emoji is four bytes, recognised as
a byte sequence exactly like a keyword written in letters, so a column after
an emoji advances by four. A tab counts as one column. Carriage returns are
ignored, so files with Windows line endings work.

## What stage 1 does not check

Stage 1 is the front end: everything below needs a symbol table or the type
of an expression, and belongs to stage 2.

- The condition of `when` is parsed as an expression; that it must be a
  `flag` is not checked yet, so `when 2 + 2:` parses.
- Overflow is checked for a number literal written next to its type. The
  value of an expression (`once int x was 3000000000 + 1.`) and of an
  assignment (`x became 3000000000.`) is not.
- That a name is declared once, before its first use, and that only a
  `once changing` variable may be assigned, is not checked.

Two test programs, `tests/ok/stage2_semantics_not_checked.txt` and
`tests/ok/stage2_overflow_not_checked.txt`, exist to record this boundary:
they are accepted here on purpose.