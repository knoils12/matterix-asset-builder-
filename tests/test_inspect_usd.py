"""以合成 USD 检查静态工具行为，不声称通过动力学验证。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pxr import Gf, Usd, UsdGeom, UsdPhysics

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_usd.py"
spec = importlib.util.spec_from_file_location("inspect_usd", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.entry = Path(self.temp.name) / "asset.usda"
        self.stage = Usd.Stage.CreateNew(str(self.entry))
        root = UsdGeom.Xform.Define(self.stage, "/Asset")
        self.stage.SetDefaultPrim(root.GetPrim())
        UsdGeom.SetStageUpAxis(self.stage, "Z")
        UsdGeom.SetStageMetersPerUnit(self.stage, 1)

    def result(self):
        self.stage.GetRootLayer().Save()
        return module.inspect(self.entry)

    def body(self, path):
        prim = UsdGeom.Xform.Define(self.stage, path).GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(prim)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(0.1)
        collider = UsdGeom.Cube.Define(self.stage, path + "/Collider")
        UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
        return prim

    def test_static_fixture_needs_no_rigid_body_or_joint(self):
        cube = UsdGeom.Cube.Define(self.stage, "/Asset/Bench")
        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
        report = self.result()
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["colliders"]), 1)
        self.assertEqual(report["rigid_bodies"], [])

    def test_free_labware(self):
        self.body("/Asset/Vial")
        report = self.result()
        self.assertEqual(report["errors"], [])
        self.assertFalse(report["rigid_bodies"][0]["kinematic"])

    def test_articulated_slider_and_inactive_connection(self):
        self.body("/Asset/Base")
        self.body("/Asset/Slider")
        joint = UsdPhysics.PrismaticJoint.Define(self.stage, "/Asset/Slide")
        joint.CreateBody0Rel().SetTargets(["/Asset/Base"])
        joint.CreateBody1Rel().SetTargets(["/Asset/Slider"])
        closure = UsdPhysics.FixedJoint.Define(self.stage, "/Asset/SpareClosure")
        closure.CreateBody1Rel().SetTargets(["/Asset/Slider"])
        closure.GetPrim().SetActive(False)
        report = self.result()
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["joints"]), 2)
        self.assertIn("/Asset/SpareClosure", report["inactive_prims"])

    def test_broken_endpoint(self):
        joint = UsdPhysics.FixedJoint.Define(self.stage, "/Asset/Bad")
        joint.CreateBody1Rel().SetTargets(["/Asset/Missing"])
        self.assertTrue(any("Missing" in error for error in self.result()["errors"]))

    def test_negative_inertia(self):
        prim = self.body("/Asset/Vial")
        UsdPhysics.MassAPI(prim).CreateDiagonalInertiaAttr(Gf.Vec3f(-1, 1, 1))
        self.assertTrue(any("惯量" in error for error in self.result()["errors"]))

    def test_unresolved_layer(self):
        self.stage.GetRootLayer().subLayerPaths.append("missing.usda")
        self.assertTrue(self.result()["unresolved"])

    def test_cli_creates_report_and_preserves_existing_report(self):
        self.result()
        output = Path(self.temp.name) / "report.json"
        command = [sys.executable, "-B", str(SCRIPT), str(self.entry), "--output", str(output)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()
        self.assertEqual(json.loads(original)["scope"], "partial_static_inspection")
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
