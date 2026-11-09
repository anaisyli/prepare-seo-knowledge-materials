"""Identify narrowly defined build outputs from their paths and file headers."""
from pathlib import Path

from package_common import long_path


REASON = "示例工程构建生成的编译产物，不作为知识资料；保留副本供核查。"


def is_build_artifact(path: Path, relative: str) -> bool:
    parts = [part.casefold() for part in relative.replace("\\", "/").split("/")]
    suffix = path.suffix.casefold()
    if suffix not in {".class", ".dex", ".o", ".exe", ".dll"}:
        return False
    with open(long_path(path), "rb") as stream:
        header = stream.read(8)
    if "intermediates" in parts and suffix == ".class":
        return header.startswith(b"\xca\xfe\xba\xbe")
    if "intermediates" in parts and suffix == ".dex":
        return header.startswith(b"dex\n")
    if ("obj" in parts or ".cxx" in parts) and suffix == ".o":
        return header.startswith(b"\x7fELF")
    if suffix in {".exe", ".dll"} and any(parts[i:i + 2] in (["bin", "debug"], ["obj", "debug"], ["bin", "release"], ["obj", "release"]) for i in range(len(parts) - 1)):
        return header.startswith(b"MZ")
    return False
