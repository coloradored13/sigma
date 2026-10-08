#!/usr/bin/env python3
"""Check the deliberately narrow Sigma Public alpha distribution allowlist.

This is a packaging/privacy guard, not general DLP or a source-code security audit.
Archives are inspected in memory and never extracted. Update the contract here
deliberately when adding modules, dependencies, scripts, or changing the release.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import re
import stat
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath

VERSION = "0.1.0a1"
LICENSE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
SDIST_GITIGNORE = b"__pycache__/\n*.py[cod]\nbuild/\ndist/\n"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_MEMBER_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 128


class DistributionError(Exception):
    """Fixed-message rejection that never prints arbitrary archive contents."""


@dataclass(frozen=True)
class Package:
    name: str
    module: str
    sources: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    entry_point: str | None = None

    @property
    def stem(self) -> str:
        return f"{self.name.replace('-', '_')}-{VERSION}"


PACKAGES = (
    Package("sigma-public-core", "sigma_public_core", (
        "__init__.py", "errors.py", "log_privacy.py", "scope.py", "workflow.py",
    )),
    Package("sigma-public-memory", "sigma_public_memory", ("__init__.py", "server.py", "store.py"), (
        f"sigma-public-core=={VERSION}", "mcp==1.30.0",
    ), "sigma_public_memory.server:main"),
    Package("sigma-public-verify", "sigma_public_verify", ("__init__.py", "server.py", "verifier.py"), (
        f"sigma-public-core=={VERSION}", "mcp==1.30.0", "httpx>=0.28,<1",
    ), "sigma_public_verify.server:main"),
    Package("sigma-public", "sigma_public", ("__init__.py", "cli.py", "controller.py"), (
        f"sigma-public-core=={VERSION}", f"sigma-public-memory=={VERSION}",
        f"sigma-public-verify=={VERSION}",
    ), "sigma_public.cli:main"),
)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise DistributionError(code)


def _safe_name(name: str, directory: bool) -> str:
    require(isinstance(name, str) and bool(name) and len(name) <= 512, "invalid_archive_path")
    require("\\" not in name and not any(ord(char) < 32 for char in name), "invalid_archive_path")
    canonical = name[:-1] if directory and name.endswith("/") else name
    require(not canonical.startswith("/"), "invalid_archive_path")
    require(all(part not in ("", ".", "..") for part in canonical.split("/")), "invalid_archive_path")
    require(":" not in canonical, "invalid_archive_path")
    return canonical


def _parents(files: set[str]) -> set[str]:
    return {str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent) != "."}


def expected_files(package: Package, kind: str) -> set[str]:
    if kind == "wheel":
        metadata = f"{package.stem}.dist-info"
        files = {f"{package.module}/{source}" for source in package.sources}
        files.update(f"{metadata}/{name}" for name in ("METADATA", "WHEEL", "RECORD", "licenses/LICENSE"))
        if package.entry_point:
            files.add(f"{metadata}/entry_points.txt")
        return files
    return {
        *(f"{package.stem}/src/{package.module}/{source}" for source in package.sources),
        *(f"{package.stem}/{name}" for name in ("pyproject.toml", "README.md", "LICENSE", "PKG-INFO", ".gitignore")),
    }


def _member(
    name: str, directory: bool, size: int, expected: set[str], seen: set[str], files: dict[str, bytes],
) -> str:
    name = _safe_name(name, directory)
    require(name not in seen, "duplicate_archive_member")
    seen.add(name)
    require(len(seen) <= MAX_MEMBERS, "too_many_archive_members")
    require(type(size) is int and 0 <= size <= MAX_MEMBER_BYTES, "archive_member_too_large")
    require(not directory or size == 0, "directory_contains_data")
    require(name in (_parents(expected) if directory else expected), "unexpected_archive_member")
    require(sum(map(len, files.values())) + size <= MAX_TOTAL_BYTES, "archive_contents_too_large")
    return name


def read_archive(path: Path, package: Package, kind: str) -> dict[str, bytes]:
    require(not path.is_symlink() and path.is_file(), "archive_must_be_regular_file")
    require(path.stat().st_size <= MAX_ARCHIVE_BYTES, "archive_too_large")
    expected = expected_files(package, kind)
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    if kind == "wheel":
        with zipfile.ZipFile(path) as archive:
            require(len(archive.infolist()) <= MAX_MEMBERS, "too_many_archive_members")
            require(not archive.comment, "unexpected_archive_metadata")
            for member in archive.infolist():
                directory = member.is_dir()
                file_type = stat.S_IFMT(member.external_attr >> 16)
                require(file_type in (0, stat.S_IFDIR if directory else stat.S_IFREG), "archive_link_or_special_file")
                require(not member.flag_bits & 1 and not member.comment, "unexpected_archive_metadata")
                # Extra fields can carry unreviewed path/owner/comment metadata.
                require(not member.extra, "unexpected_archive_metadata")
                name = _member(member.filename, directory, member.file_size, expected, seen, files)
                if not directory:
                    with archive.open(member) as stream:
                        content = stream.read(MAX_MEMBER_BYTES + 1)
                    require(len(content) == member.file_size, "archive_member_size_mismatch")
                    files[name] = content
    else:
        # Streaming iteration bounds member count and expansion before reading contents.
        with tarfile.open(path, "r|gz") as archive:
            for member in archive:
                require(member.isdir() or member.isfile(), "archive_link_or_special_file")
                require(not member.issparse(), "archive_link_or_special_file")
                require(member.uid == member.gid == 0 and member.uname in ("", "root")
                        and member.gname in ("", "root"), "unexpected_archive_owner")
                require(not (set(member.pax_headers) - {"mtime"}), "unexpected_archive_metadata")
                name = _member(member.name, member.isdir(), member.size, expected, seen, files)
                if member.isfile():
                    stream = archive.extractfile(member)
                    require(stream is not None, "unreadable_archive_member")
                    with stream:
                        content = stream.read(MAX_MEMBER_BYTES + 1)
                    require(len(content) == member.size, "archive_member_size_mismatch")
                    files[name] = content
    require(set(files) == expected, "missing_required_archive_member")
    for content in files.values():
        require(not re.search(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----", content), "private_key_marker")
    return files


def _dependencies(requirements: list[str] | tuple[str, ...]) -> dict[str, frozenset[str]]:
    found = {}
    for requirement in requirements:
        require(isinstance(requirement, str), "invalid_dependency")
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*([<>=!~0-9a-zA-Z.,+*\s-]+)", requirement)
        require(match is not None, "invalid_dependency")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        specifiers = tuple(part.strip() for part in match[2].split(","))
        require(name not in found and len(set(specifiers)) == len(specifiers), "duplicate_dependency")
        found[name] = frozenset(specifiers)
    return found


def _metadata(content: bytes, package: Package) -> None:
    message = BytesParser(policy=default).parsebytes(content)
    require(not message.defects, "invalid_package_metadata")
    allowed = {
        "metadata-version", "name", "version", "summary", "requires-python", "requires-dist",
        "license-expression", "license-file", "description-content-type",
    }
    require(all(key.lower() in allowed for key in message.keys()), "unexpected_package_metadata")
    required = {
        "Name": package.name, "Version": VERSION, "Requires-Python": ">=3.11",
        "License-Expression": "Apache-2.0", "License-File": "LICENSE",
    }
    for key, value in required.items():
        require(message.get_all(key) == [value], "package_metadata_mismatch")
    require(message.get_all("Metadata-Version") in (["2.4"], ["2.5"]), "unsupported_metadata_version")
    for key in ("Summary", "Description-Content-Type"):
        require(len(message.get_all(key, [])) <= 1, "duplicate_package_metadata")
    require(_dependencies(message.get_all("Requires-Dist", [])) == _dependencies(package.dependencies),
            "dependency_contract_mismatch")


def _license(content: bytes) -> None:
    # The unmodified Apache 2.0 text shipped at the repository root is pinned.
    require(hashlib.sha256(content).hexdigest() == LICENSE_SHA256, "license_text_mismatch")


def _wheel(files: dict[str, bytes], package: Package) -> None:
    prefix = f"{package.stem}.dist-info"
    _metadata(files[f"{prefix}/METADATA"], package)
    _license(files[f"{prefix}/licenses/LICENSE"])
    metadata = BytesParser(policy=default).parsebytes(files[f"{prefix}/WHEEL"])
    require(not metadata.defects and set(key.lower() for key in metadata) <= {
        "wheel-version", "generator", "root-is-purelib", "tag",
    }, "invalid_wheel_metadata")
    for key, value in {"Wheel-Version": "1.0", "Root-Is-Purelib": "true", "Tag": "py3-none-any"}.items():
        require(metadata.get_all(key) == [value], "wheel_metadata_mismatch")
    record_path = f"{prefix}/RECORD"
    rows = list(csv.reader(io.StringIO(files[record_path].decode("utf-8")), strict=True))
    require(len(rows) == len(files), "wheel_record_mismatch")
    seen = set()
    for row in rows:
        require(len(row) == 3 and row[0] in files and row[0] not in seen, "wheel_record_mismatch")
        name, checksum, size = row
        seen.add(name)
        if name == record_path:
            require(checksum == size == "", "wheel_record_mismatch")
        else:
            encoded = base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).rstrip(b"=").decode()
            require(checksum == f"sha256={encoded}" and size == str(len(files[name])), "wheel_record_mismatch")
    if package.entry_point:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(files[f"{prefix}/entry_points.txt"].decode("utf-8"))
        require(parser.sections() == ["console_scripts"] and not parser.defaults(), "entry_point_mismatch")
        require(dict(parser["console_scripts"]) == {package.name: package.entry_point}, "entry_point_mismatch")


def _sdist(files: dict[str, bytes], package: Package) -> None:
    prefix = package.stem
    _metadata(files[f"{prefix}/PKG-INFO"], package)
    _license(files[f"{prefix}/LICENSE"])
    require(files[f"{prefix}/.gitignore"] == SDIST_GITIGNORE, "unreviewed_sdist_ignore_file")
    document = tomllib.loads(files[f"{prefix}/pyproject.toml"].decode("utf-8"))
    require(set(document) == {"build-system", "project", "tool"}, "unexpected_project_configuration")
    project = document["project"]
    require(set(project) <= {
        "name", "version", "requires-python", "description", "license", "license-files", "readme",
        "dependencies", "scripts",
    }, "unexpected_project_configuration")
    for key, value in {
        "name": package.name, "version": VERSION, "requires-python": ">=3.11",
        "license": "Apache-2.0", "readme": "README.md",
    }.items():
        require(project.get(key) == value, "project_metadata_mismatch")
    require(project.get("license-files", ["LICENSE"]) == ["LICENSE"], "project_metadata_mismatch")
    require(_dependencies(project.get("dependencies", [])) == _dependencies(package.dependencies),
            "dependency_contract_mismatch")
    scripts = {package.name: package.entry_point} if package.entry_point else {}
    require(project.get("scripts", {}) == scripts, "entry_point_mismatch")
    require(document["build-system"] == {
        "requires": ["hatchling>=1.27,<2"], "build-backend": "hatchling.build",
    }, "unexpected_build_backend")
    tool = document["tool"]
    require(set(tool) == {"hatch"} and set(tool["hatch"]) == {"build"}, "unexpected_project_configuration")
    build = tool["hatch"]["build"]
    require(set(build) == {"targets"} and set(build["targets"]) == {"wheel", "sdist"},
            "unexpected_project_configuration")
    require(build["targets"]["wheel"] == {"packages": [f"src/{package.module}"]}, "unexpected_package_layout")
    sdist = build["targets"]["sdist"]
    require(set(sdist) == {"include"}, "unexpected_project_configuration")
    includes = sdist["include"]
    require(isinstance(includes, list) and all(isinstance(value, str) for value in includes),
            "unexpected_sdist_allowlist")
    normalized = {value[1:] if value.startswith("/") else value for value in includes}
    fixed = {"README.md", "LICENSE", "pyproject.toml", ".gitignore"}
    require(len(normalized) == len(includes) and normalized in (
        fixed | {"src"}, fixed | {f"src/{package.module}"}, fixed | {f"src/{package.module}/**/*.py"},
    ), "unexpected_sdist_allowlist")


def check_directory(directory: Path) -> list[tuple[str, str]]:
    require(not directory.is_symlink() and directory.is_dir(), "distribution_directory_missing")
    expected = {
        f"{package.stem}{suffix}": (package, kind)
        for package in PACKAGES
        for suffix, kind in (("-py3-none-any.whl", "wheel"), (".tar.gz", "sdist"))
    }
    entries = {path.name: path for path in directory.iterdir()}
    # uv build creates this exact local control file; it is not a release artifact.
    control = entries.pop(".gitignore", None)
    if control is not None:
        require(not control.is_symlink() and control.is_file() and control.stat().st_size <= 2,
                "unexpected_distribution_control_file")
        require(control.read_bytes() in (b"*", b"*\n"), "unexpected_distribution_control_file")
    require(set(entries) == set(expected), "expected_exactly_four_wheels_and_four_sdists")
    artifacts = {}
    digests = []
    for filename, (package, kind) in sorted(expected.items()):
        path = entries[filename]
        files = read_archive(path, package, kind)
        (_wheel if kind == "wheel" else _sdist)(files, package)
        artifacts[package.name, kind] = files
        with path.open("rb") as stream:
            digests.append((filename, hashlib.file_digest(stream, "sha256").hexdigest()))
    licenses = set()
    for package in PACKAGES:
        wheel, sdist = artifacts[package.name, "wheel"], artifacts[package.name, "sdist"]
        for source in package.sources:
            require(wheel[f"{package.module}/{source}"] == sdist[f"{package.stem}/src/{package.module}/{source}"],
                    "wheel_sdist_source_mismatch")
        licenses.add(wheel[f"{package.stem}.dist-info/licenses/LICENSE"])
        licenses.add(sdist[f"{package.stem}/LICENSE"])
    require(len(licenses) == 1, "license_contents_mismatch")
    return digests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        results = check_directory(args.directory)
    except DistributionError as error:
        print(f"Distribution check failed: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, tarfile.TarError, configparser.Error):
        print("Distribution check failed: malformed or unreadable artifact", file=sys.stderr)
        return 1
    for filename, digest in results:
        print(f"{digest}  {filename}")
    print("Validated four wheel/sdist pairs against the explicit release allowlist; this is not general DLP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
