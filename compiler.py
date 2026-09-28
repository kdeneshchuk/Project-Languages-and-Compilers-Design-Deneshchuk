import sys
from lexer import lex, CompileError


def main_cli():
    args = sys.argv[1:]
    if len(args) != 2 or args[0] != "--tokens":
        print("usage: compiler.py --tokens input.txt", file=sys.stderr)
        sys.exit(2)
    try:
        with open(args[1], "rb") as f:
            data = f.read()
        for tok in lex(data):
            print(f"{tok.line}:{tok.col} {tok.kind} {tok.text!r}")
    except OSError as e:
        print(f"cannot read {args[1]}: {e.strerror}", file=sys.stderr)
        sys.exit(2)
    except CompileError as e:
        print(f"compilation error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
