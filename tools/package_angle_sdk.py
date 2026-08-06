#!/usr/bin/env python3
"""Package and verify a small, relocatable ANGLE SDK for OGPlay."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT / "angle"
DEFAULT_BUILD = DEFAULT_SOURCE / "out" / "ogplay"
DEFAULT_DESTINATION = REPOSITORY_ROOT / ".local" / "angle-sdk"
DEFAULT_HEADERS = REPOSITORY_ROOT / "include"
BUILD_MANIFEST = "ogplay-angle-manifest.json"
SDK_MANIFEST = "manifest.json"
HEADER_DIRECTORIES = ("EGL", "GLES", "GLES2", "GLES3", "KHR")
LICENSE_SOURCES = (
    ("LICENSE", "ANGLE.txt"),
    ("third_party/zlib/LICENSE", "third-party/zlib.txt"),
    ("third_party/spirv-tools/src/LICENSE", "third-party/SPIRV-Tools.txt"),
    ("third_party/vulkan-loader/src/LICENSE.txt", "third-party/Vulkan-Loader.txt"),
    (
        "third_party/vulkan_memory_allocator/LICENSE.txt",
        "third-party/Vulkan-Memory-Allocator.txt",
    ),
    ("third_party/astc-encoder/src/LICENSE.txt", "third-party/ASTC-Encoder.txt"),
    ("src/common/third_party/xxhash/LICENSE", "third-party/xxHash.txt"),
)
WINDOWS_RUNTIME_FILES = ("d3dcompiler_47.dll", "vulkan-1.dll")
LINUX_RUNTIME_FILES = ("libvk_swiftshader.so", "vk_swiftshader_icd.json")
MACOS_RUNTIME_FILES = ("libvk_swiftshader.dylib", "vk_swiftshader_icd.json")

# ANGLE's Vulkan backend dlopens the Vulkan loader by basename at runtime. On
# Linux the OGPlay test executable carries a RUNPATH into the SDK lib/ dir, so
# the loader only looks there and never falls back to the system loader. The
# Vulkan loader therefore must ship next to libEGL/libGLESv2 for the SDK to be
# self-contained. Windows/macOS reach Vulkan through their own system loaders
# (vulkan-1.dll / MoltenVK) and do not need this file.
LINUX_VULKAN_LOADER = "libvulkan.so.1"


def swiftshader_runtime_files(platform_name: str, gn_args: list) -> tuple[str, ...]:
    """Return the SwiftShader runtime files required for the platform, if any.

    Windows always ships d3dcompiler/vulkan; Linux/macOS ship SwiftShader only
    when the build enabled it, matching the ANGLE SDK consumer contract.
    """
    if platform_name == "windows":
        return WINDOWS_RUNTIME_FILES
    if "angle_enable_swiftshader=true" not in gn_args:
        return ()
    if platform_name == "linux":
        return LINUX_RUNTIME_FILES
    if platform_name == "macos":
        return MACOS_RUNTIME_FILES
    return ()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read JSON manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"manifest root must be an object: {path}")
    return value


def safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe SDK path: {value!r}")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, destination_root: Path, relative: str) -> None:
    target_path = safe_relative_path(relative)
    target = destination_root.joinpath(*target_path.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_header_tree(source: Path, destination: Path) -> None:
    include = source / "include"
    for directory in HEADER_DIRECTORIES:
        header_root = include / directory
        if not header_root.is_dir():
            raise RuntimeError(f"ANGLE header directory is missing: {header_root}")
        shutil.copytree(header_root, destination / directory)


def copy_licenses(
    source: Path, destination: Path, windows_sdk_license: Path | None
) -> None:
    angle_license = source / "LICENSE"
    if not angle_license.is_file():
        raise RuntimeError(f"ANGLE license is missing: {angle_license}")
    for source_name, destination_name in LICENSE_SOURCES:
        license_path = source / source_name
        if license_path.is_file():
            copy_file(license_path, destination, f"licenses/{destination_name}")
    if windows_sdk_license is not None:
        if not windows_sdk_license.is_file():
            raise RuntimeError(f"Windows SDK license is missing: {windows_sdk_license}")
        copy_file(
            windows_sdk_license, destination, "licenses/Microsoft-Windows-SDK.rtf"
        )


def artifact_destination(platform_name: str, artifact: str) -> str:
    if platform_name == "windows":
        if artifact.endswith((".dll.lib", ".lib")):
            return f"lib/{artifact}"
        if artifact.endswith(".dll"):
            return f"bin/{artifact}"
    return f"lib/{artifact}"


def manifest_files(destination: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(item for item in destination.rglob("*") if item.is_file()):
        if path.name == SDK_MANIFEST and path.parent == destination:
            continue
        if path.name == ".DS_Store":
            continue
        relative = path.relative_to(destination).as_posix()
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256(path)})
    return files


def write_manifest(destination: Path, manifest: dict) -> None:
    (destination / SDK_MANIFEST).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def verify_manifest_files(root: Path, files: list) -> set[str]:
    if not isinstance(files, list) or not files:
        raise RuntimeError(f"manifest has no files: {root / SDK_MANIFEST}")
    declared: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise RuntimeError("manifest file entry must be an object")
        relative = safe_relative_path(str(entry.get("path", ""))).as_posix()
        if relative in declared:
            raise RuntimeError(f"duplicate manifest file: {relative}")
        declared.add(relative)
        path = root.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file():
            raise RuntimeError(f"manifest file is missing: {relative}")
        if path.stat().st_size != entry.get("size") or sha256(path) != entry.get("sha256"):
            raise RuntimeError(f"manifest file failed integrity check: {relative}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != root / SDK_MANIFEST and path.name != ".DS_Store"
    }
    extras = sorted(actual - declared)
    if extras:
        raise RuntimeError(f"directory contains undeclared files: {', '.join(extras)}")
    return declared


def git_commit(source: Path) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    return result.stdout.strip()


def package_headers(
    source: Path, destination: Path, angle_commit: str | None = None
) -> Path:
    if destination.exists():
        raise RuntimeError(f"headers destination already exists: {destination}")
    commit = angle_commit or git_commit(source)
    destination.mkdir(parents=True)
    try:
        copy_header_tree(source, destination)
        for directory in HEADER_DIRECTORIES:
            if not (destination / directory).is_dir():
                raise RuntimeError(f"packaged header directory is missing: {directory}")
        manifest = {
            "schema_version": 1,
            "kind": "headers",
            "angle_commit": commit,
            "files": manifest_files(destination),
        }
        write_manifest(destination, manifest)
        verify_headers(destination)
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def package_sdk(
    source: Path,
    build: Path,
    destination_root: Path,
    include_symbols: bool,
    windows_sdk_license: Path | None,
) -> Path:
    build_manifest = read_json(build / BUILD_MANIFEST)
    required = ("angle_commit", "platform", "target_cpu", "configuration", "gn_args")
    missing = [name for name in required if name not in build_manifest]
    if missing:
        raise RuntimeError(f"build manifest is missing: {', '.join(missing)}")
    platform_name = str(build_manifest["platform"])
    target_cpu = str(build_manifest["target_cpu"])
    configuration = str(build_manifest["configuration"])
    destination = destination_root / f"{platform_name}-{target_cpu}" / configuration
    if destination.exists():
        raise RuntimeError(f"SDK destination already exists: {destination}")
    destination.mkdir(parents=True)
    try:
        artifacts = build_manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise RuntimeError("build manifest has no artifacts")
        for name_value in artifacts:
            name = safe_relative_path(str(name_value))
            if len(name.parts) != 1:
                raise RuntimeError(f"build artifact must be a file name: {name}")
            artifact = build / name.name
            if not artifact.is_file():
                raise RuntimeError(f"build artifact is missing: {artifact}")
            copy_file(artifact, destination, artifact_destination(platform_name, name.name))
        runtime_artifacts: list[str] = []
        runtime_files = swiftshader_runtime_files(
            platform_name, build_manifest["gn_args"]
        )
        for name in runtime_files:
            runtime = build / name
            if not runtime.is_file():
                raise RuntimeError(f"ANGLE runtime dependency is missing: {runtime}")
            copy_file(runtime, destination, f"bin/{name}")
            runtime_artifacts.append(f"bin/{name}")
        if (
            platform_name == "linux"
            and "angle_enable_vulkan=true" in build_manifest["gn_args"]
        ):
            loader = build / LINUX_VULKAN_LOADER
            if not loader.is_file():
                raise RuntimeError(
                    f"ANGLE Vulkan loader dependency is missing: {loader}"
                )
            copy_file(loader, destination, f"lib/{LINUX_VULKAN_LOADER}")
        if platform_name == "windows" and include_symbols:
            for symbol in sorted(build.glob("*.pdb")):
                copy_file(symbol, destination, f"symbols/{symbol.name}")
        copy_licenses(source, destination, windows_sdk_license)
        if (destination / "include").exists():
            raise RuntimeError("platform SDK must not contain include/; use shared headers")
        manifest = {
            "schema_version": 1,
            "angle_commit": build_manifest["angle_commit"],
            "platform": platform_name,
            "target_cpu": target_cpu,
            "configuration": configuration,
            "gn_args": build_manifest["gn_args"],
            "runtime_artifacts": runtime_artifacts,
            "shared_headers": "include",
            "files": manifest_files(destination),
        }
        write_manifest(destination, manifest)
        verify_sdk(destination)
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def verify_headers(headers: Path) -> dict:
    manifest = read_json(headers / SDK_MANIFEST)
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported ANGLE headers manifest schema")
    if manifest.get("kind") != "headers":
        raise RuntimeError("headers manifest kind must be 'headers'")
    if not manifest.get("angle_commit"):
        raise RuntimeError("headers manifest is missing angle_commit")
    declared = verify_manifest_files(headers, manifest.get("files"))
    for directory in HEADER_DIRECTORIES:
        if not any(path == directory or path.startswith(f"{directory}/") for path in declared):
            raise RuntimeError(f"headers package is missing directory: {directory}")
    return manifest


def verify_sdk(sdk: Path) -> dict:
    manifest = read_json(sdk / SDK_MANIFEST)
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported ANGLE SDK manifest schema")
    if (sdk / "include").exists():
        raise RuntimeError(
            f"platform SDK must not embed include/; use shared headers instead: {sdk / 'include'}"
        )
    verify_manifest_files(sdk, manifest.get("files"))
    return manifest


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="ogplay-angle-sdk-") as temporary:
        root = Path(temporary)
        source = root / "angle"
        build = root / "build"
        for directory in HEADER_DIRECTORIES:
            header = source / "include" / directory / f"{directory.lower()}.h"
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text("/* header */\n", encoding="utf-8")
        (source / "LICENSE").write_text("license\n", encoding="utf-8")
        build.mkdir()
        artifacts = ["libEGL.dll.lib", "libEGL.dll", "libGLESv2.dll.lib", "libGLESv2.dll"]
        for name in (*artifacts, *WINDOWS_RUNTIME_FILES):
            (build / name).write_bytes(name.encode("ascii"))
        commit = "a" * 40
        (build / BUILD_MANIFEST).write_text(
            json.dumps({
                "schema_version": 1,
                "angle_commit": commit,
                "platform": "windows",
                "target_cpu": "x64",
                "configuration": "release",
                "gn_args": ["is_debug=false"],
                "artifacts": artifacts,
            }),
            encoding="utf-8",
        )
        headers = package_headers(source, root / "include", angle_commit=commit)
        headers_manifest = verify_headers(headers)
        assert headers_manifest["kind"] == "headers"
        assert headers_manifest["angle_commit"] == commit
        assert (headers / "EGL" / "egl.h").is_file()
        sdk = package_sdk(source, build, root / "sdk", False, None)
        manifest = verify_sdk(sdk)
        assert manifest["platform"] == "windows"
        assert manifest.get("shared_headers") == "include"
        assert not (sdk / "include").exists()
        assert all(not str(entry["path"]).startswith("include/") for entry in manifest["files"])
        (sdk / "bin" / "libEGL.dll").write_bytes(b"corrupt")
        try:
            verify_sdk(sdk)
        except RuntimeError as error:
            assert "integrity check" in str(error)
        else:
            raise AssertionError("corrupt SDK unexpectedly verified")
    print("ANGLE SDK packager self-test passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        choices=("package", "package-headers", "verify", "verify-headers"),
        default="package",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--build", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--headers", type=Path, default=DEFAULT_HEADERS)
    parser.add_argument("--include-symbols", action="store_true")
    parser.add_argument("--windows-sdk-license", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if args.action == "verify":
        if args.sdk is None:
            raise RuntimeError("verify requires --sdk")
        verify_sdk(args.sdk.resolve())
        print(f"verified ANGLE SDK: {args.sdk.resolve()}")
        return 0
    if args.action == "verify-headers":
        headers = args.headers.resolve()
        verify_headers(headers)
        print(f"verified ANGLE headers: {headers}")
        return 0
    if args.action == "package-headers":
        destination = package_headers(args.source.resolve(), args.headers.resolve())
        print(f"packaged ANGLE headers: {destination}")
        return 0
    destination = package_sdk(
        args.source.resolve(), args.build.resolve(), args.destination.resolve(),
        args.include_symbols, args.windows_sdk_license.resolve() if args.windows_sdk_license else None,
    )
    print(f"packaged ANGLE SDK: {destination}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ANGLE SDK packaging failed: {error}")
        raise SystemExit(1)
