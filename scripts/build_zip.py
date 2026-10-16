"""Build the deployment zip for one Lambda function.

Usage: python3 scripts/build_zip.py <function> <output.zip>

The zip root holds lambda_function.py (from src/<function>/) and the shared/
package (from src/shared/), so handlers can `from shared import ...`.
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def add_tree(zf, folder, prefix=""):
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if path.is_dir() or path.suffix == ".pyc" or "__pycache__" in relative.parts:
            continue
        zf.write(path, prefix + relative.as_posix())


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    function, output = sys.argv[1], Path(sys.argv[2])
    function_dir = SRC / function
    if not function_dir.is_dir() or function == "shared":
        print(f"Unknown function: {function}")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        add_tree(zf, function_dir)
        add_tree(zf, SRC / "shared", prefix="shared/")
    with zipfile.ZipFile(output) as zf:
        for name in zf.namelist():
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
