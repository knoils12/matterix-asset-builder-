"""验证配方构建、输入保护与搬迁打包；不执行动力学。"""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from build_asset import build
from package_asset import package


class BuildToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.geometry = self.root / "geometry" / "model.usda"
        self.geometry.parent.mkdir()
        stage = Usd.Stage.CreateNew(str(self.geometry))
        stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/Asset").GetPrim())
        UsdGeom.SetStageUpAxis(stage, "Z")
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdPhysics.SetStageKilogramsPerUnit(stage, 1)
        for name in ("Base", "Slider"):
            UsdGeom.Xform.Define(stage, "/Asset/" + name)
            cube = UsdGeom.Cube.Define(stage, "/Asset/" + name + "/Collider")
            cube.CreateSizeAttr(0.1)
        stage.GetRootLayer().Save()
        self.original = self.geometry.read_bytes()
        self.recipe = json.loads((SKILL / "assets" / "build-recipe.json").read_text())
        self.recipe_path = self.root / "recipe.json"
        self.output = self.root / "built"

    def build(self, recipe=None):
        self.recipe_path.write_text(json.dumps(self.recipe if recipe is None else recipe))
        return build(self.recipe_path, self.output)

    def test_build_physics_drive_frame_and_material_without_changing_source(self):
        entry = self.build()
        stage = Usd.Stage.Open(str(entry))
        slider = stage.GetPrimAtPath("/Asset/Slider")
        self.assertTrue(slider.HasAPI(UsdPhysics.RigidBodyAPI))
        self.assertEqual(UsdPhysics.MassAPI(slider).GetMassAttr().Get(), 1)
        self.assertAlmostEqual(UsdPhysics.MassAPI(slider).GetDiagonalInertiaAttr().Get()[0], 0.001)
        joint = UsdPhysics.PrismaticJoint(stage.GetPrimAtPath("/Asset/Joints/Slide"))
        self.assertEqual(joint.GetBody1Rel().GetTargets(), [Sdf.Path("/Asset/Slider")])
        self.assertEqual(joint.GetAxisAttr().Get(), "X")
        self.assertAlmostEqual(joint.GetUpperLimitAttr().Get(), 0.3)
        self.assertEqual(UsdPhysics.DriveAPI(joint, "linear").GetMaxForceAttr().Get(), 100)
        frame = UsdGeom.Xformable(stage.GetPrimAtPath("/Asset/Slider/grasp"))
        self.assertAlmostEqual(frame.GetLocalTransformation().ExtractTranslation()[2], 0.05)
        collider = stage.GetPrimAtPath("/Asset/Slider/Collider")
        self.assertTrue(collider.HasAPI(UsdPhysics.CollisionAPI))
        material, _ = UsdShade.MaterialBindingAPI(collider).ComputeBoundMaterial("physics")
        self.assertEqual(str(material.GetPath()), "/Asset/Materials/Contact")
        self.assertEqual(self.geometry.read_bytes(), self.original)
        record = json.loads((self.output / "build.json").read_text())
        self.assertEqual(record["scope"], "authored_not_simulated")
        self.assertEqual(record["geometry_sha256"], hashlib.sha256(self.original).hexdigest())

    def test_static_recipe_does_not_invent_bodies_or_articulation(self):
        entry = self.build({k: self.recipe[k] for k in ("schema_version", "geometry", "default_prim")})
        stage = Usd.Stage.Open(str(entry))
        self.assertFalse(any(p.HasAPI(UsdPhysics.RigidBodyAPI) or p.HasAPI(UsdPhysics.ArticulationRootAPI)
                             for p in stage.Traverse()))

    def test_invalid_recipe_does_not_publish_partial_output(self):
        bad = []
        for section, key, value in (("bodies", "mass_kg", -1), ("bodies", "kinematic", "false"),
                                    ("bodies", "path", "/Missing"), ("joints", "type", "guess")):
            recipe = copy.deepcopy(self.recipe)
            recipe[section][0][key] = value
            bad.append(recipe)
        recipe = copy.deepcopy(self.recipe)
        recipe["joints"][1]["drive"]["target_position"] = 1
        bad.append(recipe)
        recipe = copy.deepcopy(self.recipe)
        recipe["frames"][0]["orientation_xyzw"] = [0, 0, 0, 2]
        bad.append(recipe)
        for recipe in bad:
            with self.subTest(recipe=recipe), self.assertRaises((ValueError, KeyError)):
                self.build(recipe)
            self.assertFalse(self.output.exists())
        self.assertEqual(self.geometry.read_bytes(), self.original)

    def test_reject_wrong_units(self):
        stage = Usd.Stage.Open(str(self.geometry))
        UsdGeom.SetStageMetersPerUnit(stage, 0.001)
        stage.GetRootLayer().Save()
        with self.assertRaisesRegex(ValueError, "米制"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_build_refuses_existing_output(self):
        self.build()
        original = (self.output / "physics.usda").read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual((self.output / "physics.usda").read_bytes(), original)

    def test_mesh_collision_and_revolute_drive(self):
        stage = Usd.Stage.Open(str(self.geometry))
        stage.RemovePrim("/Asset/Slider/Collider")
        mesh = UsdGeom.Mesh.Define(stage, "/Asset/Slider/Collider")
        mesh.CreatePointsAttr([Gf.Vec3f(0), Gf.Vec3f(0.1, 0, 0), Gf.Vec3f(0, 0.1, 0), Gf.Vec3f(0, 0, 0.1)])
        mesh.CreateFaceVertexCountsAttr([3, 3, 3, 3])
        mesh.CreateFaceVertexIndicesAttr([0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3])
        stage.GetRootLayer().Save()
        self.recipe["colliders"][1]["approximation"] = "none"
        with self.assertRaisesRegex(ValueError, "动态 Mesh"):
            self.build()
        self.recipe["colliders"][1]["approximation"] = "convexHull"
        joint = self.recipe["joints"][1]
        joint.update(type="revolute", limits=[-90, 90])
        joint["drive"]["target_position"] = 45
        result = Usd.Stage.Open(str(self.build()))
        self.assertEqual(UsdPhysics.MeshCollisionAPI(result.GetPrimAtPath("/Asset/Slider/Collider"))
                         .GetApproximationAttr().Get(), "convexHull")
        self.assertEqual(UsdPhysics.DriveAPI(result.GetPrimAtPath("/Asset/Joints/Slide"), "angular")
                         .GetTargetPositionAttr().Get(), 45)

    def test_reject_nested_bodies(self):
        self.recipe["bodies"].append({"path": "/Asset/Slider/Collider", "mass_kg": 0.1})
        with self.assertRaisesRegex(ValueError, "嵌套刚体"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_package_relocated_preserves_inactive_connection_and_includes(self):
        resource = self.geometry.parent / "resource.bin"
        resource.write_bytes(b"\x00\x01external asset dependency")
        source = Usd.Stage.Open(str(self.geometry))
        source.GetDefaultPrim().CreateAttribute("resource", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("resource.bin"))
        source.GetRootLayer().Save()
        closure = copy.deepcopy(self.recipe["joints"][0])
        closure.update(path="/Asset/Joints/Closure", active=False)
        self.recipe["joints"].append(closure)
        entry = self.build()
        (self.root / "controller.py").write_text("# supplied runtime\n")
        (self.root / "private.sldprt").write_text("do not bundle unrelated input")
        archive = self.root / "deliver.zip"
        result = package(self.root, entry, archive, ["controller.py", "built/build.json"])
        with zipfile.ZipFile(archive) as zipped:
            self.assertIsNone(zipped.testzip())
            self.assertNotIn("private.sldprt", zipped.namelist())
            self.assertIn("controller.py", zipped.namelist())
            self.assertEqual(zipped.read("geometry/resource.bin"), resource.read_bytes())
            manifest = json.loads(zipped.read("bundle_manifest.json"))
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256(zipped.read(name)).hexdigest(), digest)
            destination = self.root / "relocated"
            zipped.extractall(destination)
        stage = Usd.Stage.Open(str(destination / manifest["entry"]))
        self.assertTrue(stage.GetPrimAtPath("/Asset/Slider").HasAPI(UsdPhysics.RigidBodyAPI))
        self.assertFalse(stage.GetPrimAtPath("/Asset/Joints/Closure").IsActive())
        stage.GetPrimAtPath("/Asset/Joints/Closure").SetActive(True)
        self.assertEqual(UsdPhysics.FixedJoint(stage.GetPrimAtPath("/Asset/Joints/Closure"))
                         .GetBody1Rel().GetTargets(), [Sdf.Path("/Asset/Base")])
        self.assertEqual(result["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        original = archive.read_bytes()
        with self.assertRaises(FileExistsError):
            package(self.root, entry, archive)
        self.assertEqual(archive.read_bytes(), original)

    def test_package_rejects_absolute_reference(self):
        entry = self.build()
        layer = Sdf.Layer.FindOrOpen(str(entry))
        layer.subLayerPaths = [str(self.output / "physics.usda"), "../geometry/model.usda"]
        layer.Save()
        with self.assertRaisesRegex(ValueError, "相对"):
            package(self.root, entry, self.root / "invalid.zip")
        self.assertFalse((self.root / "invalid.zip").exists())

    def test_package_rejects_outside_root_and_symlink(self):
        entry = self.build()
        with self.assertRaisesRegex(ValueError, "目录外"):
            package(self.output, entry, self.root / "invalid.zip")
        link = self.root / "alias.usda"
        link.symlink_to(entry)
        with self.assertRaisesRegex(ValueError, "符号链接"):
            package(self.root, link, self.root / "invalid.zip")

    def test_package_rejects_missing_dependency(self):
        entry = self.build()
        layer = Sdf.Layer.FindOrOpen(str(entry))
        layer.subLayerPaths.append("missing.usda")
        layer.Save()
        with self.assertRaisesRegex(ValueError, "未解析"):
            package(self.root, entry, self.root / "invalid.zip")

    def test_cli_build_and_package(self):
        self.recipe_path.write_text(json.dumps(self.recipe))
        build_command = [sys.executable, "-B", str(SKILL / "scripts/build_asset.py"),
                         "--recipe", str(self.recipe_path), "--output", str(self.output)]
        first = subprocess.run(build_command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        archive = self.root / "cli.zip"
        second = subprocess.run([sys.executable, "-B", str(SKILL / "scripts/package_asset.py"),
                                 "--root", str(self.root), "--entry", "built/asset.usda",
                                 "--include", "built/build.json", "--output", str(archive)],
                                capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["archive"], str(archive))


if __name__ == "__main__":
    unittest.main()
