"""Build a test-only ZIP with a private copy of the sibling protocol library."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    """Transform archive contents only; leave release imports and pins intact."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=root.parent / "py-crestron-nvx")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    component = root / "custom_components" / "crestron_nvx"
    prefix = "custom_components/crestron_nvx/"
    files: dict[str, bytes] = {}
    for path in sorted(component.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in {".py", ".json", ".png", ".svg", ".yaml"}:
            continue
        data = path.read_bytes()
        if path.suffix == ".py":
            source = data.decode().replace(
                "from crestron_nvx import", "from ._client import"
            )
            ast.parse(source)
            data = source.encode()
        files[prefix + path.relative_to(component).as_posix()] = data
    manifest = json.loads(files[prefix + "manifest.json"])
    manifest["requirements"] = []
    manifest["version"] = "0.2.0b2"
    files[prefix + "manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    library = args.library / "src" / "crestron_nvx"
    for path in sorted(library.iterdir()):
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed"):
            files[prefix + "_client/" + path.name] = path.read_bytes()
    assert prefix + "_client/__init__.py" in files
    for name in ("LICENSE", "NOTICE"):
        files[prefix + "_client/" + name] = (args.library / name).read_bytes()
        files[prefix + name] = (root / name).read_bytes()
    files[prefix + "LOCAL_TEST_BUILD.txt"] = (
        b"0.2.0b2 private test build. Bundles the unreleased crestron-nvx client.\n"
        b"No PyPI dependency or HACS release required. aiohttp/yarl come from HA.\n"
        b"Replace the complete integration directory when returning to a release.\n"
        b"Unofficial community integration; not affiliated with or supported by Crestron.\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "x", ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with ZipFile(args.output) as archive:
        assert archive.testzip() is None
    print(args.output)
    print(
        f"{len(files)} files; SHA256 {hashlib.sha256(args.output.read_bytes()).hexdigest()}"
    )


if __name__ == "__main__":
    main()
