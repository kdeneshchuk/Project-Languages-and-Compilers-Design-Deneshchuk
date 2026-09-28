import sys
from lexer import lex, CompileError
from parser import Parser

USAGE = "usage: compiler.py [--ast | --tokens] input.txt"


def main_cli():
    args = sys.argv[1:]
    mode = None
    if args and args[0] in ("--ast", "--tokens"):
        mode = args[0]
        args = args[1:]
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    if args[0].startswith("-"):
        print(f"unknown option {args[0]!r}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    try:
        with open(args[0], "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"cannot read {args[0]}: {e.strerror}", file=sys.stderr)
        sys.exit(2)

    try:
        tokens = lex(data)
        if mode == "--tokens":
            for tok in tokens:
                print(f"{tok.line}:{tok.col} {tok.kind} {tok.text!r}")
            return
        tree = Parser(tokens).parse_program()
    except CompileError as e:
        print(f"compilation error: {e}", file=sys.stderr)
        sys.exit(1)

    if mode == "--ast":
        tree.dump()


if __name__ == "__main__":
    main_cli()