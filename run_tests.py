"""Run all Telly tests: tests/ok/*.txt against .ast, tests/err/*.txt against .expected."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPILER = os.path.join(ROOT, "compiler.py")


def run(path):
    return subprocess.run([sys.executable, COMPILER, "--ast", path],
                          capture_output=True)


def read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def names(folder):
    d = os.path.join(ROOT, "tests", folder)
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".txt")), d


def main():
    failed = []
    total = 0

    ok_names, ok_dir = names("ok")
    for name in ok_names:
        total += 1
        r = run(os.path.join(ok_dir, name + ".txt"))
        expected = read(os.path.join(ok_dir, name + ".ast"))
        if r.returncode == 0 and r.stdout == expected and r.stderr == b"":
            print(f"PASS  ok/{name}")
        else:
            print(f"FAIL  ok/{name}")
            failed.append(f"ok/{name}")

    err_names, err_dir = names("err")
    for name in err_names:
        total += 1
        r = run(os.path.join(err_dir, name + ".txt"))
        expected = read(os.path.join(err_dir, name + ".expected"))
        if r.returncode == 1 and r.stdout == b"" and r.stderr == expected:
            print(f"PASS  err/{name}")
        else:
            print(f"FAIL  err/{name}")
            failed.append(f"err/{name}")

    print()
    print(f"{total - len(failed)} of {total} tests passed")
    if failed:
        print("failed:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()