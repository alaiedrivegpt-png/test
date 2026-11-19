"""Fault injection tests for the CI machinery and release verdict, separate from engineering acceptance."""
import io,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ci_support import audit_hashes, check, project_path, read_result, run_command, sha256, summarize_checks, validate_record,result_revision,require_fresh_result

class CIRunnerControls(unittest.TestCase):
    def test_silent_exit_cannot_reuse_an_old_result(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json';p.write_text('{"execution_complete":true}')
            before=result_revision(p)
            r=run_command([sys.executable,'-c','pass'],d,io.StringIO())
            self.assertEqual(r['returncode'],0)
            with self.assertRaisesRegex(ValueError,'did not refresh'):require_fresh_result(p,before)
    def test_missing_stage_result_is_execution_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'not produced'):require_fresh_result(Path(d)/'missing.json',None)
    def test_nonzero_child_process_is_retained_with_feedback(self):
        with tempfile.TemporaryDirectory() as d:
            log=io.StringIO();r=run_command([sys.executable,'-c',"import sys;print('controlled failure');sys.exit(9)"],d,log)
            self.assertEqual(r['returncode'],9)
            self.assertIn('controlled failure',log.getvalue());self.assertIn('EXIT 9',log.getvalue())
    def test_unavailable_executable_is_execution_error(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_command([str(Path(d)/'absent_solver')],d,io.StringIO())
            self.assertEqual(r['returncode'],127);self.assertIsNotNone(r['execution_error'])
    def test_missing_stl_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn('Missing: mesh/bracket.stl',audit_hashes(d,{'mesh/bracket.stl':'0'*64}))
    def test_stale_result_hash_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'solver_result.dat';p.write_text('original');h=sha256(p);p.write_text('modified')
            self.assertIn('Changed: solver_result.dat',audit_hashes(d,{'solver_result.dat':h}))
    def test_known_engineering_failure_cannot_be_green(self):
        c=[check('unit',['R16'],'PASS','Harness works'),check('mesh',['R13'],'FAIL','Convergence failed',next_action='Refine mesh')]
        counts,status,code=summarize_checks(c)
        self.assertEqual((status,code),('FAIL',1));self.assertEqual(counts['FAIL'],1)
    def test_missing_physical_evidence_cannot_be_pass(self):
        with tempfile.TemporaryDirectory() as d:
            status,_=validate_record(d,{'status':'PASS'})
            self.assertEqual(status,'BLOCKED')
    def test_blocked_only_is_nonzero(self):
        _,status,code=summarize_checks([check('physical',['R05'],'BLOCKED','Not measured')])
        self.assertEqual((status,code),('BLOCKED',2))
    def test_error_is_not_a_design_strength_failure(self):
        _,status,code=summarize_checks([check('solver',['R13'],'ERROR','Could not run')])
        self.assertEqual((status,code),('ERROR',3))
    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):project_path(d,'../private.txt')
    def test_missing_requirement_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json';p.write_text(json.dumps({'checks':[{'id':'a','status':'PASS','requirements':['R08']}]}))
            with self.assertRaisesRegex(ValueError,'missing requirement coverage'):read_result(d,'result.json',['R05','R08'])
    def test_missing_next_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json';p.write_text(json.dumps({'checks':[{'id':'a','status':'FAIL','requirements':['R05']}]}))
            with self.assertRaisesRegex(ValueError,'lacks next action'):read_result(d,'result.json',['R05'])

if __name__=='__main__':unittest.main()
