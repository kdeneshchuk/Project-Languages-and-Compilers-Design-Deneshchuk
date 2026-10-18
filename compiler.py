import os
import sys
from lexer import lex, CompileError
from parser import Parser
from semantic import SemanticChecker
from codegen import CodeGen

USAGE = ("usage: compiler.py input.txt output.ll\n"
         "       compiler.py [--ast | --tokens] input.txt")


def fail(message):
    """The one line that reports an error: stderr, exit code 1, and nothing is written."""
    print(f"compilation error: {message}", file=sys.stderr)
    sys.exit(1)

def position(parser, checker, generator):
    """Where the compiler was when something unexpected happened: the statement
    the last stage was working on, or the token the parser was looking at."""
    for stage in (generator, checker):
        node = getattr(stage, "at", None)
        if node is not None:
            return f"line {node.line}:{node.col}"
    if parser is not None and parser.tokens:
        tok = parser.peek() or parser.tokens[-1]
        return f"line {tok.line}:{tok.col}"
    return "line 1:1"

def main_cli():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    mode = None
    if args and args[0] in ("--ast", "--tokens"):
        mode = args[0]
        args = args[1:]
    if len(args) != (1 if mode else 2):
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    if args[0].startswith("-"):
        print(f"unknown option {args[0]!r}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    if mode is None and os.path.abspath(args[1]) == os.path.abspath(args[0]):
        print("refusing to overwrite the input file", file=sys.stderr)
        sys.exit(2)

    try:
        with open(args[0], "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"cannot read {args[0]}: {e.strerror}", file=sys.stderr)
        sys.exit(2)

    output = None
    module_text = None
    parser = checker = generator = None
    try:
        tokens = lex(data)
        if mode == "--tokens":
            lines = [f"{tok.line}:{tok.col} {tok.kind} {tok.text!r}" for tok in tokens]
            output = "\n".join(lines) if lines else None
        else:
            parser = Parser(tokens)
            tree = parser.parse_program()
            if mode == "--ast":
                output = "\n".join(tree.dump_lines())
            else:
                checker = SemanticChecker()
                checker.check(tree)
                generator = CodeGen()
                module_text = str(generator.generate(tree))
    except CompileError as e:
        fail(str(e))
    except RecursionError:
        fail(f"{position(parser, checker, generator)}: nesting is too deep")
    except Exception as e:                      # a bug of the compiler is never a traceback
        reason = " ".join(f"{type(e).__name__}: {e}".split())
        fail(f"{position(parser, checker, generator)}: internal error ({reason})")

    if output is not None:
        print(output)
    if module_text is not None:
        try:
            with open(args[1], "w") as f:
                f.write(module_text)
        except OSError as e:
            print(f"cannot write {args[1]}: {e.strerror}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main_cli()