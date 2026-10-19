#!/usr/bin/env python3
"""只读 USD 结构检查；不执行仿真或资产中的行为脚本。"""

import argparse
import json
import math
from pathlib import Path
import sys

try:
    from pxr import Sdf, Usd, UsdGeom, UsdPhysics, UsdUtils
except ImportError:
    print("需要 pxr：请使用带 OpenUSD 的 Python 或目标 Isaac Sim Python 环境。", file=sys.stderr)
    raise SystemExit(2)


def inspect(entry):
    entry = Path(entry).resolve(strict=True)
    stage = Usd.Stage.Open(str(entry), load=Usd.Stage.LoadAll)
    if not stage:
        raise ValueError(f"无法打开 USD: {entry}")
    report = {
        "scope": "partial_static_inspection",
        "entry": str(entry),
        "usd_version": list(Usd.GetVersion()),
        "default_prim": str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "rigid_bodies": [], "colliders": [], "joints": [],
        "inactive_prims": [], "errors": [], "warnings": [],
        "limitations": [
            "无物理仿真、碰撞 cooking、Matterix 接入或行为认证",
            "仅当前选中 variant 与可组合内容；inactive 父级下的后代可能未组合",
            "不展开实例代理；共享 prototype 内部须另查物理所有权",
        ],
    }
    if not stage.GetDefaultPrim():
        report["warnings"].append("入口没有 defaultPrim；按资产/场景用途核实")
    for key in ("metersPerUnit", "upAxis"):
        if not stage.HasAuthoredMetadata(key):
            report["warnings"].append(f"未显式声明 {key}")
    if report["meters_per_unit"] != 1 or report["up_axis"] != "Z":
        report["warnings"].append("不是规范化米制/Z-up；核实显式换算及最终 spawn")
    if not math.isfinite(report["meters_per_unit"]) or report["meters_per_unit"] <= 0:
        report["errors"].append("无效 metersPerUnit")

    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(str(entry)))
    report["layers"] = sorted(layer.identifier for layer in layers)
    report["assets"] = sorted(str(asset) for asset in assets)
    report["unresolved"] = sorted(str(asset) for asset in unresolved)
    report["errors"].extend(f"依赖未解析: {asset}" for asset in report["unresolved"])
    report["errors"].extend(str(error) for error in stage.GetCompositionErrors())

    for prim in stage.TraverseAll():
        path = str(prim.GetPath())
        if not prim.IsActive():
            report["inactive_prims"].append(path)
        if prim.IsInstance():
            report["warnings"].append(f"实例未展开: {path}")
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            body = UsdPhysics.RigidBodyAPI(prim)
            report["rigid_bodies"].append({
                "path": path, "active": prim.IsActive(),
                "enabled": body.GetRigidBodyEnabledAttr().Get(),
                "kinematic": body.GetKinematicEnabledAttr().Get(),
            })
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            report["colliders"].append({
                "path": path, "active": prim.IsActive(),
                "enabled": UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get(),
            })
        if prim.HasAPI(UsdPhysics.MassAPI):
            mass = UsdPhysics.MassAPI(prim)
            for attr in (mass.GetMassAttr(), mass.GetDiagonalInertiaAttr()):
                if attr.HasAuthoredValueOpinion():
                    value = attr.Get()
                    values = [value] if isinstance(value, (int, float)) else list(value)
                    if any(not math.isfinite(x) or x < 0 for x in values):
                        report["errors"].append(f"无效质量/对角惯量: {attr.GetPath()}")
                    elif any(x == 0 for x in values):
                        report["warnings"].append(f"含自动计算值，需 SDK 读回: {attr.GetPath()}")
        if prim.IsA(UsdPhysics.Joint):
            joint = UsdPhysics.Joint(prim)
            endpoints = [joint.GetBody0Rel().GetTargets(), joint.GetBody1Rel().GetTargets()]
            report["joints"].append({
                "path": path, "type": prim.GetTypeName(), "active": prim.IsActive(),
                "enabled": joint.GetJointEnabledAttr().Get(),
                "body0": [str(p) for p in endpoints[0]],
                "body1": [str(p) for p in endpoints[1]],
            })
            if not any(endpoints):
                report["errors"].append(f"关节两侧均未绑定: {path}")
            for targets in endpoints:
                if len(targets) > 1:
                    report["errors"].append(f"关节单侧具有多个目标: {path}")
                for target in targets:
                    if not target.IsPrimPath() or not stage.GetPrimAtPath(target):
                        report["errors"].append(f"关节目标不存在或不是 prim: {path} -> {target}")
    report["status"] = "errors_detected" if report["errors"] else "no_detected_errors"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path)
    parser.add_argument("--output", type=Path, help="新建 JSON；已存在的报告不会覆盖")
    args = parser.parse_args()
    try:
        report = inspect(args.entry)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        else:
            print(rendered, end="")
        return 1 if report["errors"] else 0
    except Exception as error:
        print(f"检查失败: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
