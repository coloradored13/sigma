"""Synthetic archives exercise publication boundaries without extracting content."""

import base64
import csv
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

SCANNER_PATH = Path(__file__).parents[1] / "tools" / "check_distributions.py"
SPEC = importlib.util.spec_from_file_location("distribution_scanner", SCANNER_PATH)
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)

LICENSE = (SCANNER_PATH.parents[1] / "LICENSE").read_bytes()


def metadata(package):
    fields = [
        "Metadata-Version: 2.4", f"Name: {package.name}", f"Version: {scanner.VERSION}",
        "Requires-Python: >=3.11", "License-Expression: Apache-2.0", "License-File: LICENSE",
        *(f"Requires-Dist: {dependency}" for dependency in package.dependencies),
    ]
    return ("\n".join(fields) + "\n\nSynthetic description.\n").encode()


def project(package):
    text = f'''[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"
[project]
name = "{package.name}"
version = "{scanner.VERSION}"
requires-python = ">=3.11"
license = "Apache-2.0"
readme = "README.md"
dependencies = {json.dumps(package.dependencies)}
'''
    if package.entry_point:
        text += f'[project.scripts]\n{package.name} = "{package.entry_point}"\n'
    text += f'''[tool.hatch.build.targets.wheel]
packages = ["src/{package.module}"]
[tool.hatch.build.targets.sdist]
include = ["src/{package.module}", "README.md", "LICENSE", "pyproject.toml", ".gitignore"]
'''
    return text.encode()


def wheel_files(package):
    files = {f"{package.module}/{name}": b'"""Synthetic fixture."""\n' for name in package.sources}
    prefix = f"{package.stem}.dist-info"
    files[f"{prefix}/METADATA"] = metadata(package)
    files[f"{prefix}/licenses/LICENSE"] = LICENSE
    files[f"{prefix}/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    if package.entry_point:
        files[f"{prefix}/entry_points.txt"] = (
            f"[console_scripts]\n{package.name} = {package.entry_point}\n"
        ).encode()
    record = io.StringIO()
    writer = csv.writer(record)
    for name, content in files.items():
        digest = base64.urlsafe_b64encode(sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow((name, f"sha256={digest}", len(content)))
    writer.writerow((f"{prefix}/RECORD", "", ""))
    files[f"{prefix}/RECORD"] = record.getvalue().encode()
    return files


def write_wheel(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def write_sdist(path, files, extra=None):
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        if extra is not None:
            archive.addfile(extra)


@pytest.fixture
def release(tmp_path):
    for package in scanner.PACKAGES:
        wheel_path = tmp_path / f"{package.stem}-py3-none-any.whl"
        write_wheel(wheel_path, wheel_files(package))
        files = {f"{package.stem}/src/{package.module}/{name}": b'"""Synthetic fixture."""\n'
                 for name in package.sources}
        files.update({f"{package.stem}/pyproject.toml": project(package),
                      f"{package.stem}/.gitignore": scanner.SDIST_GITIGNORE,
                      f"{package.stem}/LICENSE": LICENSE,
                      f"{package.stem}/README.md": b"Synthetic description.\n",
                      f"{package.stem}/PKG-INFO": metadata(package)})
        write_sdist(tmp_path / f"{package.stem}.tar.gz", files)
    return tmp_path


def test_complete_release_reports_only_filenames_and_hashes(release, capsys):
    results = scanner.check_directory(release)
    assert len(results) == 8
    assert all(len(digest) == 64 for _, digest in results)
    assert scanner.main([str(release)]) == 0
    output = capsys.readouterr().out
    assert "Synthetic description" not in output
    assert "not general DLP" in output


@pytest.mark.parametrize("name", ["../../escaped", "sigma_public_core/.env", "sigma_public_core/private.sqlite",
                                 "sigma_public_core/extra.py", "/etc/private", "sigma_public_core\\secret"])
def test_unexpected_paths_fail_without_extraction(release, name):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}-py3-none-any.whl"
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(name, "SYNTHETIC-PRIVATE-CANARY")
    with pytest.raises(scanner.DistributionError):
        scanner.check_directory(release)
    assert not (release.parent / "escaped").exists()


def test_symlink_member_rejected(release):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}-py3-none-any.whl"
    files = wheel_files(package)
    name = f"{package.module}/scope.py"
    del files[name]
    write_wheel(path, files)
    link = zipfile.ZipInfo(name)
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(link, "/synthetic/private")
    with pytest.raises(scanner.DistributionError, match="archive_link_or_special_file"):
        scanner.check_directory(release)


def test_tar_hard_link_rejected(release):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}.tar.gz"
    files = scanner.read_archive(path, package, "sdist")
    name = f"{package.stem}/src/{package.module}/scope.py"
    del files[name]
    link = tarfile.TarInfo(name)
    link.type = tarfile.LNKTYPE
    link.linkname = "../../synthetic-private"
    write_sdist(path, files, link)
    with pytest.raises(scanner.DistributionError, match="archive_link_or_special_file"):
        scanner.check_directory(release)


def test_version_or_dependency_change_rejected(release):
    package = scanner.PACKAGES[1]
    path = release / f"{package.stem}-py3-none-any.whl"
    files = wheel_files(package)
    meta = f"{package.stem}.dist-info/METADATA"
    files[meta] = files[meta].replace(b"sigma-public-core==0.1.0a1", b"sigma-public-core>=0.0.1")
    write_wheel(path, files)
    with pytest.raises(scanner.DistributionError, match="dependency_contract_mismatch"):
        scanner.check_directory(release)


def test_private_key_inside_allowed_source_fails_without_echo(release, capsys):
    package = scanner.PACKAGES[0]
    files = wheel_files(package)
    files[f"{package.module}/scope.py"] = b"-----BEGIN PRIVATE KEY-----\nSYNTHETIC-PRIVATE-CANARY"
    write_wheel(release / f"{package.stem}-py3-none-any.whl", files)
    assert scanner.main([str(release)]) == 1
    output = capsys.readouterr()
    assert "CANARY" not in output.err + output.out
    assert "private_key_marker" in output.err


def test_member_expansion_limit(release, monkeypatch):
    monkeypatch.setattr(scanner, "MAX_MEMBER_BYTES", 32)
    with pytest.raises(scanner.DistributionError, match="archive_member_too_large"):
        scanner.check_directory(release)


def test_missing_artifact_rejected(release):
    next(release.glob("*.whl")).unlink()
    with pytest.raises(scanner.DistributionError, match="expected_exactly_four"):
        scanner.check_directory(release)


def test_source_tampering_detected_by_record(release):
    package = scanner.PACKAGES[0]
    files = wheel_files(package)
    files[f"{package.module}/scope.py"] = b"# changed after RECORD generation\n"
    write_wheel(release / f"{package.stem}-py3-none-any.whl", files)
    with pytest.raises(scanner.DistributionError, match="wheel_record_mismatch"):
        scanner.check_directory(release)


def test_sdist_source_must_match_wheel(release):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}.tar.gz"
    files = scanner.read_archive(path, package, "sdist")
    files[f"{package.stem}/src/{package.module}/scope.py"] = b"# differing sdist source\n"
    write_sdist(path, files)
    with pytest.raises(scanner.DistributionError, match="wheel_sdist_source_mismatch"):
        scanner.check_directory(release)


def test_license_must_be_the_complete_reviewed_text(release):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}.tar.gz"
    files = scanner.read_archive(path, package, "sdist")
    files[f"{package.stem}/LICENSE"] = b"Apache License Version 2.0, January 2004 END OF TERMS AND CONDITIONS"
    write_sdist(path, files)
    with pytest.raises(scanner.DistributionError, match="license_text_mismatch"):
        scanner.check_directory(release)


def test_directory_entry_cannot_hide_content(release):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}-py3-none-any.whl"
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(f"{package.module}/", "SYNTHETIC-PRIVATE-CANARY")
    with pytest.raises(scanner.DistributionError, match="directory_contains_data"):
        scanner.check_directory(release)


def test_sdist_ignore_file_cannot_carry_parent_configuration(release):
    package = scanner.PACKAGES[0]
    path = release / f"{package.stem}.tar.gz"
    files = scanner.read_archive(path, package, "sdist")
    files[f"{package.stem}/.gitignore"] += b"SYNTHETIC-PRIVATE-CANARY\n"
    write_sdist(path, files)
    with pytest.raises(scanner.DistributionError, match="unreviewed_sdist_ignore_file"):
        scanner.check_directory(release)
