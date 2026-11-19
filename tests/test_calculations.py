"""Independent mathematical, physical-scaling and parser-failure tests for v1."""
import copy,importlib.util,json,math,unittest,tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def load(name,rel):
 spec=importlib.util.spec_from_file_location(name,ROOT/rel);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
calc=load('v1_calculation_tests','scripts/calculate.py')
fem=load('v1_fem_tests','scripts/run_fem.py')
class AnalyticalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.cfg=json.loads((ROOT/'config/design.json').read_text())
 def test_rounded_section_against_independent_slice_quadrature(self):
  b,r=38.1,3.175;y=np.linspace(-b/2,b/2,200001);c=b/2-r;w=np.where(abs(y)<=c,b,2*(c+np.sqrt(np.maximum(0,r*r-(abs(y)-c)**2))));A,I=calc.rounded_square(b,r)
  self.assertAlmostEqual(np.trapezoid(w,y)/A,1,places=7);self.assertAlmostEqual(np.trapezoid(w*y*y,y)/I,1,places=7)
 def test_zero_radius_reduces_to_square(self):
  a,i=calc.rounded_square(12,0);self.assertEqual(a,144);self.assertEqual(i,12**4/12)
 def test_tube_section_matches_independent_exact_CAD_volume(self):
  m=json.loads((ROOT/'cad/geometry_manifest.json').read_text());b=self.cfg['beam'];A,I=calc.tube_section(b['outer_mm'],b['wall_mm'],b['outer_radius_mm'],b['inner_radius_mm'])
  self.assertAlmostEqual(A*b['length_mm']/m['geometry']['beam_400mm']['volume_mm3'],1,places=9)
 def test_invalid_geometry_rejected(self):
  for args in [(10,6),(10,-1)]:
   with self.assertRaises(ValueError):calc.rounded_square(*args)
  with self.assertRaises(ValueError):calc.tube_section(10,6,1,1)
 def test_chamfer_formula_matches_polygon_shoelace(self):
  b,c=31.55,3;h=b/2;v=np.array([[-h+c,-h],[h-c,-h],[h,-h+c],[h,h-c],[h-c,h],[-h+c,h],[-h,h-c],[-h,-h+c]]);n=np.roll(v,-1,axis=0);cross=v[:,0]*n[:,1]-n[:,0]*v[:,1];a=.5*cross.sum();i=(cross*(v[:,1]**2+v[:,1]*n[:,1]+n[:,1]**2)).sum()/12
  aa,ii=calc.chamfered_square(b,c);self.assertAlmostEqual(a,aa,places=8);self.assertAlmostEqual(i,ii,places=7)
 def test_mass_unit_conversion(self):
  v=calc.calculate(self.cfg)['values'];expected=v['section_Amax_mm2']*400.5*1e-9*2800*9.80665;self.assertAlmostEqual(v['beam_weight_upper_N'],expected,places=10)
 def test_increased_service_load_cannot_pass_unchanged_envelope(self):
  c=copy.deepcopy(self.cfg);c['loads']['service_force_N']=250;r=calc.calculate(c);item=next(x for x in r['checks'] if x['id']=='calc:bracket_force_envelope');self.assertEqual(item['status'],'FAIL');self.assertTrue(item['next_action'])
 def test_fixture_stack_failure_detected(self):
  c=copy.deepcopy(self.cfg);c['anchors']['sleeve_length_mm']=25;r=calc.calculate(c);self.assertEqual(next(x['status'] for x in r['checks'] if x['id']=='calc:fixture_thickness'),'FAIL')
 def test_actual_dimensions_are_not_physical_acceptance(self):
  r=calc.calculate(self.cfg);self.assertNotIn('physical_qualification_pass',r);self.assertTrue(any('physical' in s.lower() for s in r['assumptions']))
 def test_bearing_force_uses_couple_arm(self):
  r=calc.calculate(self.cfg)['values'];self.assertAlmostEqual(r['contact_force_N'],100);self.assertGreater(r['contact_force_N'],self.cfg['loads']['bracket_force_envelope_N'])
class StressAndEvidenceTests(unittest.TestCase):
 def test_vm_zero_hydrostatic_but_principal_not_zero(self):
  s=np.array([[30,30,30,0,0,0]]);self.assertEqual(fem.vm(s)[0],0);self.assertEqual(fem.spectral(s)[0],30)
 def test_pure_shear(self):
  s=np.array([[0,0,0,5,0,0]]);self.assertAlmostEqual(fem.vm(s)[0],math.sqrt(3)*5);self.assertAlmostEqual(fem.spectral(s)[0],5)
 def test_direction_bound_dominates_random_load_combinations(self):
  rng=np.random.default_rng(41);s=rng.normal(size=(6,30,6));vbound=fem.direction_bound([fem.vm(x) for x in s]);pbound=fem.direction_bound([fem.spectral(x) for x in s]);f=rng.normal(size=3);f/=np.linalg.norm(f);m=rng.normal(size=2);m/=np.linalg.norm(m);combined=np.einsum('i,ijk->jk',np.r_[f,.7,m],s)
  self.assertTrue(np.all(fem.vm(combined)<=vbound+1e-12));self.assertTrue(np.all(fem.spectral(combined)<=pbound+1e-12))
 def test_DAT_shear_reordering(self):
  keys,s=fem.parse_dat_stress(' stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz)\n\n 7 2 1 2 3 4 5 6\n');self.assertEqual(keys.tolist(),[[7,2]]);self.assertEqual(s.tolist(),[[1,2,3,4,6,5]])
 def test_missing_solver_fields_rejected(self):
  with self.assertRaises(ValueError):fem.parse_frd('No results')
  with self.assertRaises(ValueError):fem.parse_dat_stress('Only a heading')
 def test_solver_failure_does_not_pass(self):
  self.assertFalse(fem.solver_finished('Job finished',1));self.assertFalse(fem.solver_finished('*ERROR material\nJob finished',0));self.assertFalse(fem.solver_finished('Started',0));self.assertTrue(fem.solver_finished('Job finished',0))
 def test_actual_failed_solver_invocation_is_rejected(self):
  c=json.loads((ROOT/'config/design.json').read_text())
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);solver=r/'fail_solver';solver.write_text('#!/usr/bin/env python3\nimport sys\nprint("Deliberate solver failure fixture")\nsys.exit(7)\n');solver.chmod(0o755)
   xyz=np.array([[45.8,y,z] for y in [-1,1] for z in [-1,1]],float);mesh={'meta':{'part':'bracket','label':'failure_fixture'},'xyz':xyz,'node_ids':np.arange(1,5)}
   with self.assertRaisesRegex(RuntimeError,'exit7'):fem.execute_case(r,mesh,c,'fx',b'** controlled negative test\n',[],solver)
   self.assertIn('Deliberate solver failure fixture',(r/'fem/failure_fixture/fx.solver.log').read_text())
 def test_quadratic_face_pressure_integrates_exact_patch_and_centroid(self):
  points=np.array([[-20,-20],[20,-20],[0,20]],float);w,a=fem.clipped_triangle_load_weights(points,(-5,5,-5,5));nodes=np.vstack([points,(points[0]+points[1])/2,(points[1]+points[2])/2,(points[2]+points[0])/2]);self.assertAlmostEqual(a,100,places=10);self.assertAlmostEqual(w.sum(),100,places=10);self.assertTrue(np.allclose(w@nodes,[0,0],atol=1e-10))
 def test_quadratic_face_complete_triangle_has_zero_corner_loads(self):
  w,a=fem.clipped_triangle_load_weights(np.array([[0,0],[2,0],[0,2]],float),(0,2,0,2));self.assertTrue(np.allclose(w[:3],0,atol=1e-12));self.assertTrue(np.allclose(w[3:],2/3,atol=1e-12))
 def test_consistent_gravity_conserves_force_and_moment(self):
  c=json.loads((ROOT/'config/design.json').read_text());corners=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float);edges=[(0,1),(1,2),(2,0),(0,3),(1,3),(2,3)];xyz=np.vstack([corners]+[(corners[a]+corners[b])/2 for a,b in edges]);mesh={'node_ids':np.arange(1,11),'xyz':xyz,'elements':np.arange(1,11).reshape(1,10),'meta':{'FE_volume_mm3':1/6}};f=fem.consistent_gravity_nodes(mesh,c);W=c['beam']['density_kg_m3']*c['loads']['gravity_m_s2']*1e-9/6;self.assertTrue(np.allclose(f.sum(axis=0),[0,0,-W],atol=1e-15));self.assertTrue(np.allclose(np.cross(xyz,f).sum(axis=0),[-W/4,W/4,0],atol=1e-15));self.assertTrue(np.all(f[:4,2]>0))
 def test_balanced_tip_load_resultants(self):
  c=json.loads((ROOT/'config/design.json').read_text());xyz=np.array([[45.8,y,z] for y in [-10,0,10] for z in [-10,0,10]],float);mesh={'xyz':xyz,'node_ids':np.arange(1,10)};loads=fem.balanced_tip_load(mesh,c,'my');ff=np.zeros((9,3))
  for n,d,f in loads:ff[n-1,d-1]=f
  self.assertTrue(np.allclose(ff.sum(axis=0),0,atol=1e-10));self.assertTrue(np.allclose(np.cross(xyz-[45.8,0,0],ff).sum(axis=0),[0,1600,0],atol=1e-9))
if __name__=='__main__':unittest.main()
