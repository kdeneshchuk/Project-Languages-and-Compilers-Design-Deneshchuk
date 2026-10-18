"""Runs every test in tests/ok and tests/err and says which ones failed.

tests/ok/NAME.txt   a valid program
    NAME.ast        (optional) the expected `compiler.py --ast` output
    NAME.expected   (optional) the expected standard output of the compiled
                    program; with it the test is end to end: compile, build, run
    NAME.in         (optional) the standard input of the compiled program
tests/err/NAME.txt  an invalid program
    NAME.expected   the expected error line (stderr of the compiler)
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPILER = os.path.join(ROOT, "compiler.py")
TIMEOUT = 20


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


def run(cmd, stdin=b""):
    return subprocess.run(cmd, input=stdin, capture_output=True, timeout=TIMEOUT)


def compile_program(source, out_ll):
    return run([sys.executable, COMPILER, source, out_ll])


def execute(ll_path, tmp, stdin):
    """Run a .ll file: with lli if there is one, else build it with llc and clang."""
    if shutil.which("lli"):
        return run(["lli", ll_path], stdin)
    obj, exe = os.path.join(tmp, "program.o"), os.path.join(tmp, "program")
    built = run(["llc", "-filetype=obj", "-relocation-model=pic", ll_path, "-o", obj])
    if built.returncode == 0:
        built = run(["clang", obj, "-o", exe])
    if built.returncode != 0:
        return built
    return run([exe], stdin)


def check_ast(name_path):
    expected = read_text(name_path + ".ast")
    got = run([sys.executable, COMPILER, "--ast", name_path + ".txt"])
    if got.returncode != 0:
        return f"--ast failed: {got.stderr.decode('utf-8', 'replace').strip()}"
    if got.stdout.decode("utf-8") != expected:
        return "the AST differs from the .ast file"
    return None


def check_run(name_path):
    """Compile into a temporary directory (never next to the tests), run, compare."""
    stdin = b""
    if os.path.exists(name_path + ".in"):
        with open(name_path + ".in", "rb") as f:
            stdin = f.read()
    expected = read_text(name_path + ".expected")
    with tempfile.TemporaryDirectory() as tmp:
        ll = os.path.join(tmp, "out.ll")
        built = compile_program(name_path + ".txt", ll)
        if built.returncode != 0:
            return f"does not compile: {built.stderr.decode('utf-8', 'replace').strip()}"
        done = execute(ll, tmp, stdin)
        if done.returncode != 0:
            return f"the build or the run failed (code {done.returncode}): " \
                   f"{done.stderr.decode('utf-8', 'replace').strip()}"
        got = done.stdout.decode("utf-8", "replace")
        if got != expected:
            return f"output differs\n      expected: {expected!r}\n      got:      {got!r}"
    return None


def check_error(name_path):
    expected = read_text(name_path + ".expected").rstrip("\n")
    with tempfile.TemporaryDirectory() as tmp:
        ll = os.path.join(tmp, "out.ll")
        got = compile_program(name_path + ".txt", ll)
        if got.returncode != 1:
            return f"expected exit code 1, got {got.returncode}"
        if os.path.exists(ll):
            return "the compiler wrote an .ll file for an invalid program"
    line = got.stderr.decode("utf-8", "replace").rstrip("\n")
    if line != expected:
        return f"error line differs\n      expected: {expected!r}\n      got:      {line!r}"
    return None


def main():
    failed = []
    counts = {"valid": 0, "invalid": 0, "end to end": 0}

    def report(label, name, problem):
        print(f"{'PASS' if problem is None else 'FAIL'}  {label:5} {name}")
        if problem is not None:
            print(f"      {problem}")
            failed.append(f"{label}/{name}")

    for src in sorted(glob.glob(os.path.join(ROOT, "tests", "ok", "*.txt"))):
        base = src[:-4]
        name = os.path.basename(base)
        counts["valid"] += 1
        checks = []
        if os.path.exists(base + ".ast"):
            checks.append(check_ast)
        if os.path.exists(base + ".expected"):
            checks.append(check_run)
            counts["end to end"] += 1
        problem = None
        for check in checks:
            problem = check(base)
            if problem:
                break
        report("ok", name, problem)

    for src in sorted(glob.glob(os.path.join(ROOT, "tests", "err", "*.txt"))):
        base = src[:-4]
        counts["invalid"] += 1
        report("err", os.path.basename(base), check_error(base))

    total = counts["valid"] + counts["invalid"]
    print(f"\n{total - len(failed)}/{total} passed "
          f"({counts['valid']} valid, {counts['end to end']} of them end to end, "
          f"{counts['invalid']} invalid)")
    if failed:
        print("failed:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()