#!/usr/bin/env python3
"""保留分层 USD，收集本地相对依赖与指定附加文件，验证后创建 ZIP。"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import sys
import tempfile
import zipfile

from inspect_usd import inspect
from pxr import Sdf, UsdUtils


def package(root, entry, output, includes=()):
    root = Path(root).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"输出已存在: {output}")

    def local_file(value):
        candidate = Path(os.path.abspath(root / value))
        if not candidate.is_relative_to(root):
            raise ValueError(f"文件在包根目录外: {value}")
        for part in (candidate, *candidate.parents):
            if part == root:
                break
            if part.is_symlink():
                raise ValueError(f"请先将符号链接整理为独立文件: {value}")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"不是包内普通文件: {value}")
        return resolved

    entry = local_file(entry)
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(str(entry)))
    if unresolved:
        raise ValueError(f"依赖未解析，请补齐或显式整理系统资源: {unresolved}")
    files = {entry, *(local_file(layer.realPath) for layer in layers),
             *(local_file(asset) for asset in assets), *(local_file(item) for item in includes)}
    for layer in layers:
        clone = Sdf.Layer.CreateAnonymous()
        clone.TransferContent(layer)

        def check_path(value):
            if value:
                if Path(value).is_absolute() or PureWindowsPath(value).is_absolute() or "://" in value:
                    raise ValueError(f"请先改为本地相对资产引用: {value}")
                if "<UDIM>" in value or "${" in value:
                    raise ValueError(f"需专用资源整理器处理模板路径: {value}")
                local_file(Sdf.ComputeAssetPathRelativeToLayer(layer, value))
            return value

        UsdUtils.ModifyAssetPaths(clone, check_path)
    if any(path.relative_to(root).as_posix() == "bundle_manifest.json" for path in files):
        raise ValueError("bundle_manifest.json 是打包器保留文件名")
    with tempfile.TemporaryDirectory(prefix="matterix-package-") as directory:
        staging = Path(directory) / "bundle"
        staging.mkdir()
        hashes = {}
        for filename in sorted(files):
            relative = filename.relative_to(root)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filename, destination)
            hashes[relative.as_posix()] = hashlib.sha256(destination.read_bytes()).hexdigest()
        report = inspect(staging / entry.relative_to(root))
        if report["errors"]:
            raise ValueError(f"复制后 USD 校验失败: {report['errors']}")
        manifest = {"entry": entry.relative_to(root).as_posix(), "sha256": hashes,
                    "scope": "dependency_copy_and_partial_static_inspection",
                    "warnings": report["warnings"],
                    "runtime": "未执行；附加脚本/配置的动态依赖由 --include 显式提供"}
        (staging / "bundle_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        archive = Path(directory) / "asset.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for filename in sorted(staging.rglob("*")):
                if filename.is_file():
                    zipped.write(filename, filename.relative_to(staging).as_posix())
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip():
                raise ValueError("ZIP CRC 校验失败")
        output.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with output.open("xb") as dst:
                created = True
                with archive.open("rb") as src:
                    shutil.copyfileobj(src, dst)
        except BaseException:
            if created:
                output.unlink()
            raise
    return {"archive": str(output), "file_count": len(files) + 1,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="依赖必须位于此目录内")
    parser.add_argument("--entry", required=True, type=Path, help="相对 root 的入口")
    parser.add_argument("--output", required=True, type=Path, help="尚不存在的 ZIP")
    parser.add_argument("--include", action="append", default=[], help="显式附加的包内普通文件，可重复")
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.root, args.entry, args.output, args.include), ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"打包失败: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
