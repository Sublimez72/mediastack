import sys

from . import apply, prep


def main():
    args = sys.argv[1:] or ["apply"]
    if args[0] == "prep":
        prep.run()
        return 0
    if args[0] == "apply":
        return apply.run(dry_run="--dry-run" in args)
    print("usage: stackinit [prep | apply [--dry-run]]")
    return 2


sys.exit(main())
