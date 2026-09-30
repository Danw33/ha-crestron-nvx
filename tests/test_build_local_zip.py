"""Private ZIPs must not mutate release sources or require a published client."""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import build_local_zip


def prepare(tmp_path, monkeypatch, version):
    component = tmp_path / "ha/custom_components/crestron_nvx"
    library = tmp_path / "lib/src/crestron_nvx"
    component.mkdir(parents=True)
    library.mkdir(parents=True)
    (component / "__init__.py").write_text("from crestron_nvx import NvxClient\n")
    manifest = {"version": "0.7.0", "requirements": ["crestron-nvx==0.4.0"]}
    (component / "manifest.json").write_text(json.dumps(manifest))
    (library / "__init__.py").write_text("class NvxClient: pass\n")
    (library / "py.typed").touch()
    for root in (tmp_path / "ha", tmp_path / "lib"):
        for name in ("LICENSE", "NOTICE"):
            (root / name).write_text("Synthetic test licence")
    output = tmp_path / "private.zip"
    monkeypatch.setattr(
        build_local_zip, "__file__", str(tmp_path / "ha/scripts/build_local_zip.py")
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_local_zip",
            "--library",
            str(tmp_path / "lib"),
            "--version",
            version,
            "--output",
            str(output),
        ],
    )
    return component, output, manifest


def test_private_build_is_self_contained_and_non_mutating(tmp_path, monkeypatch):
    component, output, manifest = prepare(tmp_path, monkeypatch, "0.7.0b3")
    build_local_zip.main()
    assert json.loads((component / "manifest.json").read_text()) == manifest
    assert (
        component / "__init__.py"
    ).read_text() == "from crestron_nvx import NvxClient\n"
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        prefix = "custom_components/crestron_nvx/"
        built = json.loads(archive.read(prefix + "manifest.json"))
        assert built["version"] == "0.7.0b3"
        assert built["requirements"] == []
        assert b"from ._client import" in archive.read(prefix + "__init__.py")
        assert prefix + "_client/py.typed" in archive.namelist()
        assert prefix + "_client/LICENSE" in archive.namelist()
        assert all(
            not Path(name).is_absolute() and ".." not in Path(name).parts
            for name in archive.namelist()
        )
    with pytest.raises(FileExistsError):
        build_local_zip.main()


@pytest.mark.parametrize("version", ["0.7.0", "latest", "../0.7.0b1", "0.7.0b"])
def test_reject_non_prerelease_versions(tmp_path, monkeypatch, version):
    _, output, _ = prepare(tmp_path, monkeypatch, version)
    with pytest.raises(SystemExit):
        build_local_zip.main()
    assert not output.exists()
