#!/usr/bin/env python3
"""Actual-kernel positive and negative controls for the fit checker.

These test the detector. A successful negative control does not approve the
engineering design or replace the full geometric-fit/physical-acceptance gates.
"""
from __future__ import annotations
import importlib.util,json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fit_checker',ROOT/'scripts/check_geometric_fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)

class ActualKernelFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tube=cq.importers.importStep(str(ROOT/'cad/beam_400mm.step')).val()
        cls.core=cq.importers.importStep(str(ROOT/'cad/bracket_structural_core_only.step')).val()
        cls.printed=cq.importers.importStep(str(ROOT/'cad/bracket.step')).val()
        cls.ribs=cq.importers.importStep(str(ROOT/'cad/bracket_added_ribs.step')).val()
        cls.right=cq.importers.importStep(str(ROOT/'cad/bracket_right.step')).val()
        cls.cfg=json.loads((ROOT/'config/design.json').read_text())

    def test_nominal_core_has_real_clearance(self):
        r=fit.collision_check(self.core,self.tube)
        self.assertEqual(r['status'],'PASS')
        self.assertAlmostEqual(r['observed']['intersection_volume_mm3'],0,places=7)
        self.assertAlmostEqual(r['observed']['minimum_distance_mm'],0.1,places=6)

    def test_closed_step_solid_uses_shell_closure_not_cached_solid_flag(self):
        ok,r=fit.solid_check(self.tube)
        self.assertTrue(ok)
        self.assertTrue(r['closed'])
        self.assertEqual(r['solids'],1)

    def test_surface_cannot_pass_as_closed_solid(self):
        face=cq.Face.makePlane(10,10)
        ok,r=fit.solid_check(face)
        self.assertFalse(ok)
        self.assertEqual(r['solids'],0)

    def test_oversized_core_is_detected(self):
        oversized=self.core.transformGeometry(cq.Matrix([[1,0,0,0],[0,1.05,0,0],[0,0,1.05,0],[0,0,0,1]]))
        r=fit.collision_check(oversized,self.tube)
        self.assertEqual(r['status'],'FAIL')
        self.assertGreater(r['observed']['intersection_volume_mm3'],1)
        self.assertTrue(r['next_action'])
        self.assertIn('R15',r['requirements'])

    def test_lateral_misalignment_is_detected(self):
        r=fit.collision_check(self.core.translate((0,0.8,0)),self.tube)
        self.assertEqual(r['status'],'FAIL')
        self.assertGreater(r['observed']['intersection_volume_mm3'],1)
        self.assertIsNotNone(r['observed']['intersection_bbox_mm'])

    def test_wrong_right_instance_is_detected(self):
        expected=self.printed.rotate((0,0,0),(0,0,1),180).translate((self.cfg['assembly']['right_wall_x_mm'],0,0))
        self.assertEqual(fit.pose_check(self.right,expected)['status'],'PASS')
        r=fit.pose_check(self.right.translate((0.5,0,0)),expected)
        self.assertEqual(r['status'],'FAIL')
        self.assertGreater(r['observed']['symmetric_difference_volume_mm3'],1)

    def test_intended_ribs_are_not_misclassified_as_core_collision(self):
        overlap=fit.common_shape(self.printed,self.tube)
        self.assertGreater(fit.volume(overlap),0.5)
        self.assertLess(fit.volume(fit.cut_shape(overlap,self.ribs)),0.001)
        self.assertEqual(fit.collision_check(self.core,self.tube)['status'],'PASS')

    def test_misplaced_washer_is_detected_even_without_plate_collision(self):
        washers=cq.importers.importStep(str(ROOT/'cad/retention_washers.step')).val()
        self.assertEqual(fit.hardware_pose_check(washers,'retention_washers',self.cfg)['status'],'PASS')
        shifted=washers.translate((0,2,0))
        self.assertLess(fit.volume(fit.common_shape(shifted,self.core)),0.001)
        r=fit.hardware_pose_check(shifted,'retention_washers',self.cfg)
        self.assertEqual(r['status'],'FAIL')
        self.assertAlmostEqual(r['observed']['maximum_position_error_mm'],2,places=6)
        self.assertTrue(r['next_action'])

    def test_missing_delivered_step_causes_error_and_saved_feedback(self):
        with tempfile.TemporaryDirectory(prefix='fit_negative_') as td:
            root=Path(td);(root/'config').mkdir();(root/'cad').mkdir()
            shutil.copy2(ROOT/'config/design.json',root/'config/design.json')
            shutil.copy2(ROOT/'cad/geometry_manifest.json',root/'cad/geometry_manifest.json')
            completed=subprocess.run([sys.executable,str(ROOT/'scripts/check_geometric_fit.py'),'--root',str(root)],text=True,capture_output=True,timeout=60)
            self.assertEqual(completed.returncode,3,completed.stdout+completed.stderr)
            data=json.loads((root/'results/geometric_fit.json').read_text())
            self.assertFalse(data['execution_complete'])
            self.assertEqual(data['summary']['ERROR'],1)
            self.assertIn('Missing delivered STEP solid',data['checks'][0]['message'])
            self.assertTrue(data['checks'][0]['next_action'])

if __name__=='__main__':unittest.main(verbosity=2)
