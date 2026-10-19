#!/usr/bin/env python3
"""按显式 JSON 配方新建 USD 物理覆盖层，保留输入几何。"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

from inspect_usd import inspect
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade


def keys(item, allowed):
    if not isinstance(item, dict) or set(item) - set(allowed.split()):
        raise ValueError(f"对象类型或字段不支持: {item}")


def number(value, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"需要有限数值: {value}")
    if (minimum is not None and value < minimum) or (positive and value <= 0):
        raise ValueError(f"数值超出范围: {value}")
    return float(value)


def vector(values, length):
    if not isinstance(values, list) or len(values) != length:
        raise ValueError(f"需要 {length} 个分量: {values}")
    return [number(value) for value in values]


def rotation(values):
    x, y, z, w = vector(values, 4)
    if abs(x*x + y*y + z*z + w*w - 1) > 1e-5:
        raise ValueError("四元数须为归一化 xyzw")
    return Gf.Quatf(w, Gf.Vec3f(x, y, z))


def build(recipe_path, output):
    recipe_path = Path(recipe_path).resolve(strict=True)
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    keys(recipe, "schema_version geometry default_prim bodies colliders materials joints frames articulation_root sources")
    if type(recipe["schema_version"]) is not int or recipe["schema_version"] != 1:
        raise ValueError("仅支持 schema_version=1")
    geometry = (recipe_path.parent / recipe["geometry"]).resolve(strict=True)
    source = Usd.Stage.Open(str(geometry))
    if UsdGeom.GetStageMetersPerUnit(source) != 1 or UsdGeom.GetStageUpAxis(source) != "Z":
        raise ValueError("请先将源几何显式规范为米制/Z-up；本脚本不推断或改变源尺度")
    if UsdPhysics.GetStageKilogramsPerUnit(source) != 1:
        raise ValueError("请先规范源质量单位为 kg")
    root = Sdf.Path(recipe["default_prim"])
    if not root.IsPrimPath() or root.GetParentPath() != Sdf.Path.absoluteRootPath:
        raise ValueError("default_prim 必须是顶层绝对 prim 路径")
    if not source.GetPrimAtPath(root):
        raise ValueError(f"源根节点不存在: {root}")
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"输出已存在: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="matterix-build-", dir=output.parent) as directory:
        working = Path(directory)
        physics = Sdf.Layer.CreateNew(str(working / "physics.usda"))
        stage = Usd.Stage.CreateNew(str(working / "asset.usda"))
        stage.GetRootLayer().subLayerPaths = [
            "physics.usda", os.path.relpath(geometry, output).replace(os.sep, "/")]
        # 两目录同层，源路径在输出目录之外，相对引用在发布前后保持一致。
        stage.SetDefaultPrim(stage.GetPrimAtPath(root))
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, "Z")
        UsdPhysics.SetStageKilogramsPerUnit(stage, 1)
        stage.SetEditTarget(physics)

        def path(value):
            result = Sdf.Path(value)
            if not result.IsAbsolutePath() or not result.IsPrimPath() or not result.HasPrefix(root):
                raise ValueError(f"路径须在 {root} 内: {value}")
            return result

        def existing(value):
            prim = stage.GetPrimAtPath(path(value))
            if not prim or not prim.IsActive() or prim.IsInstanceProxy():
                raise ValueError(f"节点不存在、未激活或为实例代理: {value}")
            return prim

        def new_path(value):
            result = path(value)
            if stage.GetPrimAtPath(result):
                raise ValueError(f"新增节点已存在: {value}")
            return result

        for item in recipe.get("bodies", []):
            keys(item, "path mass_kg center_of_mass_m diagonal_inertia_kg_m2 principal_axes_xyzw kinematic source")
            prim = existing(item["path"])
            if not prim.IsA(UsdGeom.Xformable):
                raise ValueError(f"刚体须为可变换节点: {prim.GetPath()}")
            body = UsdPhysics.RigidBodyAPI.Apply(prim)
            body.CreateRigidBodyEnabledAttr(True)
            if type(item.get("kinematic", False)) is not bool:
                raise ValueError("kinematic 须为 JSON 布尔值")
            body.CreateKinematicEnabledAttr(item.get("kinematic", False))
            mass = UsdPhysics.MassAPI.Apply(prim)
            mass.CreateMassAttr(number(item["mass_kg"], positive=True))
            if "center_of_mass_m" in item:
                mass.CreateCenterOfMassAttr(Gf.Vec3f(*vector(item["center_of_mass_m"], 3)))
            if "diagonal_inertia_kg_m2" in item:
                inertia = [number(v, positive=True) for v in vector(item["diagonal_inertia_kg_m2"], 3)]
                if 2 * max(inertia) > sum(inertia) + 1e-10:
                    raise ValueError("主惯量不满足三角不等式")
                mass.CreateDiagonalInertiaAttr(Gf.Vec3f(*inertia))
            if "principal_axes_xyzw" in item:
                mass.CreatePrincipalAxesAttr(rotation(item["principal_axes_xyzw"]))

        for item in recipe.get("materials", []):
            keys(item, "path static_friction dynamic_friction restitution source")
            material = UsdShade.Material.Define(stage, new_path(item["path"]))
            api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
            api.CreateStaticFrictionAttr(number(item["static_friction"], minimum=0))
            api.CreateDynamicFrictionAttr(number(item["dynamic_friction"], minimum=0))
            restitution = number(item["restitution"], minimum=0)
            if restitution > 1:
                raise ValueError("恢复系数须在 [0,1] 内")
            api.CreateRestitutionAttr(restitution)

        for item in recipe.get("colliders", []):
            keys(item, "path approximation material source")
            prim = existing(item["path"])
            supported = (UsdGeom.Mesh, UsdGeom.Cube, UsdGeom.Sphere, UsdGeom.Capsule, UsdGeom.Cylinder, UsdGeom.Cone)
            if not any(prim.IsA(schema) for schema in supported):
                raise ValueError(f"不支持的碰撞几何: {prim.GetPath()}")
            UsdPhysics.CollisionAPI.Apply(prim).CreateCollisionEnabledAttr(True)
            if prim.IsA(UsdGeom.Mesh):
                approximation = item["approximation"]
                if approximation not in ("none", "convexHull", "convexDecomposition"):
                    raise ValueError("支持 none/convexHull/convexDecomposition；其他后端方案需专用构建器")
                ancestor = prim
                while ancestor and not ancestor.HasAPI(UsdPhysics.RigidBodyAPI):
                    ancestor = ancestor.GetParent()
                if approximation == "none" and ancestor and not UsdPhysics.RigidBodyAPI(ancestor).GetKinematicEnabledAttr().Get():
                    raise ValueError("普通动态 Mesh 不支持未近似三角网格；请选择实际支持的代理")
                UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr(approximation)
            elif "approximation" in item:
                raise ValueError("primitive 碰撞体不使用 Mesh approximation")
            if "material" in item:
                material = UsdShade.Material(existing(item["material"]))
                if not material or not material.GetPrim().HasAPI(UsdPhysics.MaterialAPI):
                    raise ValueError("物理材质无效")
                UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, materialPurpose="physics")

        factories = {"fixed": UsdPhysics.FixedJoint, "prismatic": UsdPhysics.PrismaticJoint,
                     "revolute": UsdPhysics.RevoluteJoint}
        for item in recipe.get("joints", []):
            keys(item, "path type body0 body1 local_pos0_m local_pos1_m local_rot0_xyzw local_rot1_xyzw axis limits drive active source")
            factory = factories[item["type"]]
            joint = factory.Define(stage, new_path(item["path"]))
            if not item.get("body0") and not item.get("body1"):
                raise ValueError("关节至少一侧须连接刚体")
            for index in (0, 1):
                target = item.get(f"body{index}")
                if target:
                    prim = existing(target)
                    if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        raise ValueError(f"关节端点不是刚体: {target}")
                    getattr(joint, f"CreateBody{index}Rel")().SetTargets([prim.GetPath()])
                getattr(joint, f"CreateLocalPos{index}Attr")(Gf.Vec3f(*vector(item[f"local_pos{index}_m"], 3)))
                getattr(joint, f"CreateLocalRot{index}Attr")(rotation(item[f"local_rot{index}_xyzw"]))
            if item["type"] != "fixed":
                if item["axis"] not in ("X", "Y", "Z"):
                    raise ValueError("轴须为关节局部 X/Y/Z")
                lower, upper = vector(item["limits"], 2)
                if lower > upper:
                    raise ValueError("配方要求有限且有序的关节限位")
                joint.CreateAxisAttr(item["axis"])
                joint.CreateLowerLimitAttr(lower)
                joint.CreateUpperLimitAttr(upper)
            elif any(key in item for key in ("axis", "limits", "drive")):
                raise ValueError("fixed 关节不接受轴、限位或驱动")
            if "drive" in item:
                drive = item["drive"]
                keys(drive, "type stiffness damping max_force target_position target_velocity")
                if drive["type"] not in ("force", "acceleration"):
                    raise ValueError("Drive type 须为 force/acceleration")
                position = number(drive["target_position"])
                if not lower <= position <= upper:
                    raise ValueError("驱动目标超出限位")
                api = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "linear" if item["type"] == "prismatic" else "angular")
                api.CreateTypeAttr(drive["type"])
                api.CreateStiffnessAttr(number(drive["stiffness"], minimum=0))
                api.CreateDampingAttr(number(drive["damping"], minimum=0))
                api.CreateMaxForceAttr(number(drive["max_force"], positive=True))
                api.CreateTargetPositionAttr(position)
                api.CreateTargetVelocityAttr(number(drive.get("target_velocity", 0)))
            if type(item.get("active", True)) is not bool:
                raise ValueError("active 须为 JSON 布尔值")
            joint.GetPrim().SetActive(item.get("active", True))

        for item in recipe.get("frames", []):
            keys(item, "path position_m orientation_xyzw source")
            frame_path = new_path(item["path"])
            existing(str(frame_path.GetParentPath()))
            frame = UsdGeom.Xform.Define(stage, frame_path)
            frame.AddTranslateOp().Set(Gf.Vec3d(*vector(item["position_m"], 3)))
            frame.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(rotation(item["orientation_xyzw"]))
        if recipe.get("articulation_root"):
            UsdPhysics.ArticulationRootAPI.Apply(existing(recipe["articulation_root"]))
        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                ancestor = prim.GetParent()
                while ancestor:
                    if ancestor.HasAPI(UsdPhysics.RigidBodyAPI):
                        raise ValueError(f"本构建器不支持嵌套刚体，请先整理 Link: {prim.GetPath()}")
                    ancestor = ancestor.GetParent()
        physics.Save()
        stage.GetRootLayer().Save()
        report = inspect(working / "asset.usda")
        if report["errors"]:
            raise ValueError(report["errors"])
        record = {"scope": "authored_not_simulated", "recipe": recipe,
                  "recipe_sha256": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
                  "geometry_sha256": hashlib.sha256(geometry.read_bytes()).hexdigest(),
                  "usd_version": list(Usd.GetVersion()), "warnings": report["warnings"]}
        (working / "build.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.mkdir()
        created = []
        try:
            for name in ("asset.usda", "physics.usda", "build.json"):
                destination = output / name
                with (working / name).open("rb") as src, destination.open("xb") as dst:
                    created.append(destination)
                    shutil.copyfileobj(src, dst)
        except BaseException:
            for filename in created:
                filename.unlink()
            if not list(output.iterdir()):
                output.rmdir()
            raise
    return output / "asset.usda"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="尚不存在的输出目录")
    args = parser.parse_args()
    try:
        print(build(args.recipe, args.output))
        return 0
    except Exception as error:
        print(f"构建失败: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
