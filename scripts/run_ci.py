#!/usr/bin/env python3
"""Single local/hosted CI entry point. Every run saves full logs and actionable requirements feedback.

Exit 0=all acceptance gates PASS; 1=engineering/artifact FAIL; 2=physical BLOCKED; 3=execution ERROR.
--mode selftest returns the test-system verdict only, explicitly not an engineering release.
"""
from __future__ import annotations
import argparse,csv,importlib,importlib.metadata,json,os,re,sys
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
from ci_support import check,now,project_path,read_result,run_command,sha256,summarize_checks,validate_record,audit_hashes,result_revision,require_fresh_result

DEFAULT_ROOT=Path(__file__).resolve().parents[1]
REQUIREMENTS={
 'R01':'Self-contained version ZIP and frozen layout','R02':'400 mm beam','R03':'Two printed press-fit brackets',
 'R04':'Bolted mounts on two walls','R05':'10 N structural requirement','R06':'Catalogue section and material evidence',
 'R07':'Native Google Doc report','R08':'Full executable calculations','R09':'Priced BOM with links',
 'R10':'3D FEM stress results','R11':'Native FreeCAD CAD','R12':'Gmsh STL generation','R13':'Executed CalculiX FEM',
 'R14':'Automatic requirements audit and feedback','R15':'CadQuery and Open CASCADE fit checks',
 'R16':'Functional CI and meaningful negative tests','R17':'Saved CI logs and next-iteration feedback',
 'R18':'Simple AI reference','R19':'Explicit reconstruction provenance'}

REQUIRED_FILES={
 'README.md':['R01','R17'], 'requirement.md':['R01','R14'], 'AI_REFERENCE.md':['R18'],
 'CHANGELOG.md':['R01','R19'], 'config/design.json':['R02','R08'], 'config/physical_acceptance.json':['R05','R14'],
 'requirements.lock':['R01','R16'], '.github/workflows/ci.yml':['R16','R17'],
 'scripts/build_cad.py':['R11'], 'scripts/check_geometric_fit.py':['R15'], 'scripts/calculate.py':['R08'],
 'scripts/run_fem.py':['R12','R13'], 'scripts/run_ci.py':['R14','R16','R17'], 'scripts/ci_support.py':['R16'],
 'scripts/render_fem.py':['R10'], 'results/fem_render.json':['R10'],
 'scripts/package_project.py':['R01'], 'tests/test_geometric_fit.py':['R15','R16'],
 'tests/test_calculations.py':['R08','R16'], 'tests/test_ci_runner.py':['R16'],
 'cad/beam_400mm.step':['R02','R06'], 'cad/bracket.step':['R03','R11'],
 'cad/bracket_structural_core_only.step':['R11','R13'], 'cad/assembly.step':['R04','R11'],
 'cad/geometry_manifest.json':['R11'], 'mesh/bracket.stl':['R12'],
 'bom.csv':['R09'], 'evidence/source_manifest.json':['R06'],
 'evidence/reconstruction_provenance.json':['R19'], 'evidence/v0_report_export.docx':['R19'],
 'manufacturing/PRINT_AND_ASSEMBLY.md':['R03','R04','R05'],
 'report/report.md':['R07','R08'], 'report/report.docx':['R07'], 'report/google_doc.json':['R07'],
 'report/source_snapshot.json':['R07','R08'], 'report/visual_review.json':['R07'],
 'results/bracket_stress.png':['R10'], 'results/beam_stress.png':['R10'], 'results/stress_viewer.html':['R10']}

class CI:
    def __init__(self,root,mode):
        self.root=Path(root).resolve();self.mode=mode;self.checks=[];self.stages=[];self.sources={};self.versions={}
        runtime=self.root.parent/'.v1_runtime'
        if runtime.exists():sys.path.append(str(runtime))
        self.env=os.environ.copy();self.env['PYTHONDONTWRITEBYTECODE']='1';self.env['OMP_NUM_THREADS']='1'
        if runtime.exists():self.env['PYTHONPATH']=str(runtime)+os.pathsep+self.env.get('PYTHONPATH','')
        self.run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        (self.root/'logs').mkdir(exist_ok=True);(self.root/'results').mkdir(exist_ok=True)
        self.log_relative='logs/ci_'+self.run_id+'.log';self.log=(self.root/self.log_relative).open('w',encoding='utf-8')
        self.log.write('Beam wall mount v1 CI\nRun '+self.run_id+'\nMode '+mode+'\n')
        self.functional=True;self.unit_count=0
        self.executed_sources={}
        self.manifest_before=None
        if (self.root/'MANIFEST.sha256').is_file():
            try:
                hashes={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (self.root/'MANIFEST.sha256').read_text().splitlines() if line.strip()}
                self.manifest_before={'files':len(hashes),'issues':audit_hashes(self.root,hashes)}
            except Exception as exc:self.manifest_before={'files':0,'issues':[str(exc)]}

    def record(self,*args,**kwargs):
        c=check(*args,**kwargs);self.checks.append(c)
        self.log.write(c['status']+' '+c['id']+' '+c['message']+'\n');self.log.flush()
        return c

    def remember_sources(self):
        names=['config/design.json','requirement.md','scripts/run_ci.py','scripts/ci_support.py','scripts/build_cad.py','scripts/calculate.py','scripts/check_geometric_fit.py','scripts/run_fem.py','scripts/render_fem.py']
        names += [p.relative_to(self.root).as_posix() for p in sorted((self.root/'tests').glob('test_*.py'))]
        for name in names:
            if (self.root/name).is_file():self.executed_sources.setdefault(name,sha256(self.root/name))

    def guarded(self,name,function):
        try:function()
        except Exception as exc:
            self.functional=False
            self.record('execution:'+name,['R14','R16'],'ERROR',str(exc),category='execution',
                        next_action='Repair '+name+' using the saved exception and rerun this CI command.',evidence=[self.log_relative])

    def dependencies(self):
        names={'cadquery':'cadquery','cadquery-ocp':'OCP','gmsh':'gmsh','numpy':'numpy','matplotlib':'matplotlib','cad-ccx':'cad_ccx'}
        for dist,module in names.items():
            try:
                imported=importlib.import_module(module);v=importlib.metadata.version(dist);self.versions[dist]=v
                self.record('dependency:'+dist,['R16'],'PASS','Runtime dependency imported.',category='execution',observed=v,criterion='Importable tested dependency')
            except Exception as exc:
                self.functional=False
                self.record('dependency:'+dist,['R16'],'ERROR',str(exc),category='execution',next_action='Install requirements.lock with Python 3.12 and retry.')
        self.versions['python']=sys.version
        try:
            import OCP
            self.versions['OpenCASCADE_binding_reported']=getattr(OCP,'__version__','unknown')
        except ImportError:pass
        self.log.write('TOOL VERSIONS '+json.dumps(self.versions,sort_keys=True)+'\n')

    def units(self):
        self.remember_sources()
        result=run_command([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],self.root,self.log,env=self.env,timeout=600)
        m=re.search(r'Ran\s+(\d+)\s+tests?',result['stdout']+'\n'+result['stderr'])
        self.unit_count=int(m.group(1)) if m else 0
        transcript=result['stdout']+'\n'+result['stderr']
        mandatory_modules=['test_ci_runner','test_calculations','test_geometric_fit']
        modules_executed=all(name+'.' in transcript for name in mandatory_modules)
        ok=result['returncode']==0 and self.unit_count>=20 and modules_executed
        self.functional=self.functional and ok
        self.stages.append({k:v for k,v in result.items() if k not in ['stdout','stderr']}|{'name':'unit_and_negative_tests','test_count':self.unit_count})
        self.record('unit_and_negative_tests',['R08','R15','R16'],'PASS' if ok else 'ERROR',
                    'Independent unit tests and deliberate-negative controls executed.',category='execution',
                    observed={'exit_code':result['returncode'],'tests_run':self.unit_count,'mandatory_test_modules_executed':modules_executed},criterion='All three mandatory test modules executed; at least 20 tests; exit 0',
                    next_action='' if ok else 'Inspect the unittest failures in the CI log; repair implementation or fixtures without disabling controls.',evidence=[self.log_relative])

    def computational_stage(self,name,command,result_path,requirements):
        self.remember_sources()
        before=result_revision(self.root/result_path)
        result=run_command(command,self.root,self.log,env=self.env,timeout=2700)
        self.stages.append({k:v for k,v in result.items() if k not in ['stdout','stderr']}|{'name':name,'result':result_path})
        try:
            if result['returncode'] not in [0,1,2]:raise ValueError('Stage return code '+str(result['returncode'])+'; inspect stdout/stderr.')
            require_fresh_result(self.root/result_path,before)
            data=read_result(self.root,result_path,requirements)
            self.functional=self.functional and not any(c['status']=='ERROR' for c in data['checks'])
            self.sources[name]=data
            for c in data['checks']:
                c=dict(c);c['id']=name+':'+c['id'];c.setdefault('category','geometry' if name=='geometric_fit' else 'numerical' if name in ['calculations','fem'] else 'artifact')
                self.checks.append(c)
            self.record('stage_executed:'+name,requirements+['R16'],'PASS','Stage executed and fresh result provenance verified.',category='execution',
                        observed={'exit_code':result['returncode'],'checks':len(data['checks'])},criterion='Valid, current, mapped checks with actionable feedback',evidence=[result_path,self.log_relative])
        except Exception as exc:
            self.functional=False
            self.record('stage_executed:'+name,requirements+['R16'],'ERROR',str(exc),category='execution',
                        next_action='Inspect '+self.log_relative+' and repair '+result_path+' or its producing command. Do not replace a missing/stale result with PASS.',evidence=[self.log_relative])

    def artifacts(self):
        for name,reqs in REQUIRED_FILES.items():
            p=self.root/name;ok=p.is_file() and p.stat().st_size>0
            self.record('file:'+name,reqs,'PASS' if ok else 'FAIL','Required deliverable exists.' if ok else 'Required deliverable is absent or empty.',
                        observed=name,criterion='Present, nonempty project file',next_action='' if ok else 'Create or restore '+name+' and rerun the artifact audit.',evidence=[name] if ok else [])
        frozen=self.root/'frozen_requirements.sha256'
        ok=frozen.is_file() and frozen.read_text().split()[0]==sha256(self.root/'requirement.md')
        self.record('frozen_requirements',['R01','R14'],'PASS' if ok else 'FAIL','Frozen requirements hash matches the current baseline.',
                    criterion='Exact SHA-256 match',next_action='' if ok else 'Restore the frozen baseline or create a documented new version; do not silently edit acceptance criteria.')
        manifest=self.root/'MANIFEST.sha256'
        if manifest.exists():
            hashes={line.split('  ',1)[1]:line.split('  ',1)[0] for line in manifest.read_text().splitlines() if line.strip()}
            problems=self.manifest_before['issues'] if self.mode=='full' and self.manifest_before is not None else audit_hashes(self.root,hashes)
            message='Frozen static bytes verified before intentional full recomputation; refreeze newly generated outputs before packaging.' if self.mode=='full' else 'Static manifest byte hashes checked.'
            self.record('static_manifest',['R01'],'PASS' if not problems else 'FAIL',message,observed=problems,
                        criterion='No changed/missing static file',next_action='' if not problems else 'Restore changed files or rebuild an explicitly versioned package before freezing.',evidence=['MANIFEST.sha256'])
        else:
            self.record('static_manifest',['R01'],'FAIL','Final static manifest has not been created.',next_action='Run python scripts/package_project.py --freeze --manifest-only after all static deliverables are ready.')
        self.evidence_checks();self.bom_checks();self.report_snapshot_checks();self.google_doc_checks();self.workflow_checks()

    def report_snapshot_checks(self):
        p=self.root/'report/source_snapshot.json'
        if p.is_file():
            snap=json.loads(p.read_text());issues=audit_hashes(self.root,snap.get('static_file_hashes',{}))
            if snap.get('draft') is not False:issues.append('Report is still marked as a draft.')
            calc=self.root/'results/calculations.json'
            if calc.exists() and snap.get('calculation_values')!=json.loads(calc.read_text()).get('values'):issues.append('Report calculation values differ from fresh calculation output.')
            for source,key in [('results/geometric_fit.json','fit_checks'),('results/fem_summary.json','FEM_checks')]:
                f=self.root/source
                if f.exists():
                    current={x['id']:x['status'] for x in json.loads(f.read_text()).get('checks',[])}
                    reported={x['id']:x['status'] for x in snap.get(key,[])}
                    if current!=reported:issues.append('Report verification statuses differ from '+source)
            self.record('report_current_sources',['R07','R08'],'PASS' if not issues else 'FAIL','Report source hashes, fresh calculation values and verification statuses checked.',observed=issues,
                        criterion='Final report matches current static evidence and engineering decision',next_action='' if not issues else 'Rebuild and visually verify the report after finalizing the cited sources and results, then recreate its Google Doc receipt.',evidence=['report/source_snapshot.json'])
        review=self.root/'report/visual_review.json'
        if review.is_file():
            v=json.loads(review.read_text());docx=self.root/'report/report.docx';pdf=self.root/'report/report.pdf'
            ok=v.get('reviewed_all_pages') is True and v.get('page_count',0)>0 and v.get('title_sanitize_pass') is True
            ok=ok and docx.exists() and v.get('docx_sha256')==sha256(docx) and pdf.exists() and v.get('pdf_sha256')==sha256(pdf)
            self.record('report_visual_qa',['R07'],'PASS' if ok else 'FAIL','Final report layout review is bound to the delivered DOCX and PDF.',criterion='Every page inspected; hashes current; title sanitation passes',
                        next_action='' if ok else 'Render and inspect the final report, correct layout issues and update the actual review receipt.',evidence=['report/visual_review.json'])

    def evidence_checks(self):
        p=self.root/'evidence/source_manifest.json'
        if not p.is_file():return
        data=json.loads(p.read_text());items=data.get('sources',data.get('files',[])) if isinstance(data,dict) else data
        issues=[]
        for item in items:
            name=item.get('path',item.get('file',item.get('local_path')));wanted=item.get('sha256');url=item.get('url',item.get('source_url'))
            if not name or not wanted or not url:issues.append('Source record lacks path, hash or URL');continue
            try:
                path=project_path(self.root,name)
                if not path.is_file() or sha256(path)!=wanted:issues.append('Missing/changed source '+name)
            except ValueError as exc:issues.append(str(exc))
        ok=len(items)>=5 and not issues
        self.record('source_evidence',['R06','R09'],'PASS' if ok else 'FAIL','Stored catalogue/material evidence is independently hash checked.',
                    observed={'sources':len(items),'issues':issues},criterion='At least five sourced, hash-bound records',next_action='' if ok else 'Restore original supplier evidence and complete source_manifest path/hash/URL records.',evidence=['evidence/source_manifest.json'])

    def bom_checks(self):
        p=self.root/'bom.csv'
        if not p.is_file():return
        rows=list(csv.DictReader(p.open(newline='')));issues=[]
        fields=set(rows[0]) if rows else set()
        for alternatives in [{'part_number','catalogue_id','catalogue_number'},{'url','purchase_url','purchase_link'},{'currency'},{'unit_cost','unit_price','unit_price_currency','unit_price_original_currency'},{'notes'}]:
            if not fields&alternatives:issues.append('Missing BOM column family: '+str(sorted(alternatives)))
        links=[v for row in rows for v in row.values() if isinstance(v,str) and v.startswith('http')]
        if len(rows)<5 or len(links)<5:issues.append('At least five purchased items and links required.')
        self.record('bom_content',['R09'],'PASS' if not issues else 'FAIL','BOM schema and purchase links checked.',observed={'rows':len(rows),'issues':issues},
                    criterion='Part numbers, prices, currency, links and notes',next_action='' if not issues else 'Complete the identified BOM fields with sourced values; keep currencies and historical quotes explicit.',evidence=['bom.csv'])

    def google_doc_checks(self):
        p=self.root/'report/google_doc.json'
        if not p.is_file():return
        r=json.loads(p.read_text());ident=r.get('document_id');url=r.get('url','');md=self.root/'report/report.md';docx=self.root/'report/report.docx'
        evidence=r.get('evidence_files',[])
        ok=bool(ident) and url.startswith('https://docs.google.com/document/d/'+ident) and r.get('mime_type')=='application/vnd.google-apps.document' and r.get('verified_readback') is True
        ok=ok and md.is_file() and sha256(md)==r.get('report_markdown_sha256') and docx.is_file() and sha256(docx)==r.get('report_docx_sha256')
        ok=ok and bool(evidence) and all(project_path(self.root,x).is_file() and project_path(self.root,x).stat().st_size>0 for x in evidence)
        self.record('native_google_doc',['R07'],'PASS' if ok else 'FAIL','Native document identity, readback evidence and offline report hash checked.',observed={'url':url},
                    criterion='Actual native Google Doc with current verified readback',next_action='' if ok else 'Publish/read back the actual v1 native report and retain its receipt, rather than reusing the v0 link as a v1 result.',evidence=['report/google_doc.json'])

    def workflow_checks(self):
        p=self.root/'.github/workflows/ci.yml'
        if not p.exists():return
        text=p.read_text();ok='scripts/run_ci.py' in text and 'if: always()' in text and 'upload-artifact' in text and 'continue-on-error' not in text
        try:
            import yaml
            obj=yaml.safe_load(text);ok=ok and isinstance(obj,dict) and isinstance(obj.get('jobs'),dict)
        except Exception:ok=False
        self.record('hosted_workflow_definition',['R16','R17'],'PASS' if ok else 'FAIL','Workflow syntax and shared entry point checked; logs are retained after failures.',
                    criterion='Runnable job definition, shared CI command, always-upload evidence, no ignored failures',next_action='' if ok else 'Repair the workflow and rerun YAML/entry-point checks.',evidence=['.github/workflows/ci.yml'])

    def physical(self):
        p=self.root/'config/physical_acceptance.json';a=json.loads(p.read_text());cfg=json.loads((self.root/'config/design.json').read_text())
        mapping={'beam_length_mm':['R02'],'beam_lot_certificate':['R06'],'tube_openings_both_ends_mm':['R03'],'selected_fit_coupon':['R03'],
                 'press_fit_insertion_and_retention':['R03','R05'],'printed_process_and_material':['R03','R05'],
                 'actual_wall_and_anchor_installation':['R04','R05'],'sleeve_projection_all_four_mm':['R04','R05'],
                 'assembly_30N_proof_test':['R05'],'sustained_load_environment':['R05'],'current_procurement_quotes':['R09']}
        for key,reqs in mapping.items():
            value=a.get(key);status='BLOCKED';message='No actual physical observation has been recorded.'
            if value is not None:
                if key=='beam_length_mm':
                    valid=isinstance(value,(float,int)) and not isinstance(value,bool) and abs(value-400)<=0.5
                    status='PASS' if valid else 'FAIL';message='Actual finished beam length checked.'
                elif key=='sleeve_projection_all_four_mm':
                    valid=isinstance(value,list) and len(value)==4 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and x>=cfg['anchors']['minimum_sleeve_projection_mm'] for x in value)
                    status='PASS' if valid else 'FAIL';message='All four actual sleeve projections checked.'
                elif key=='tube_openings_both_ends_mm':
                    valid=isinstance(value,list) and len(value)==2 and all(isinstance(row,list) and len(row)==2 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and x>0 for x in row) for row in value)
                    status='PASS' if valid else 'FAIL';message='Both orthogonal opening dimensions at both ends recorded; selected fit and retention are separate gates.'
                else:status,message=validate_record(self.root,value)
                if key=='assembly_30N_proof_test' and status=='PASS' and value.get('load_N',0)<30:
                    status='FAIL';message='Proof record does not establish a measured load of at least 30 N.'
            self.record('physical:'+key,reqs,status,message,category='physical',observed=value,criterion='Authentic recorded measurement/test evidence',
                        next_action='' if status=='PASS' else 'Perform and document '+key.replace('_',' ')+'. Record observations, operator/date and evidence; simulation cannot approve this gate.',evidence=['config/physical_acceptance.json'])
        status,message=validate_record(self.root,{'status':'PASS','operator':a.get('operator'),'date':a.get('test_date'),'evidence_files':a.get('evidence_files',[])})
        self.record('physical:provenance',['R02','R03','R04','R05','R06'],status,message,category='physical',
                    next_action='' if status=='PASS' else 'Add genuine operator, date and retained evidence after actual qualification.',evidence=['config/physical_acceptance.json'])

    def finish(self):
        changed=audit_hashes(self.root,self.executed_sources)
        if changed:
            self.functional=False
        self.record('execution_sources_stable',['R14','R16'],'PASS' if not changed else 'ERROR','Code, tests, requirements and configuration stayed unchanged during this CI run.',category='execution',observed=changed,
                    criterion='No source mutations during execution',next_action='' if not changed else 'Finish source edits, then rerun the complete CI entry point against a stable snapshot.')
        self.record('ci_saved_log',['R17'],'PASS','Full stdout/stderr, commands, timings and exit codes saved in a separate run log.',evidence=[self.log_relative])
        if self.mode!='selftest':
            self.record('feedback_outputs',['R14','R17'],'PASS','Structured summary and next-iteration feedback are written by this finalization step.',evidence=['results/ci_summary.json','results/next_iteration.md'])
        else:
            self.record('selftest_summary',['R16','R17'],'PASS','Test-system-only summary written; engineering acceptance is not evaluated in this mode.',evidence=['results/selftest_summary.json'])
        if self.mode!='selftest':
            covered={r for c in self.checks for r in c['requirements']};missing=sorted(set(REQUIREMENTS)-covered)
            self.record('all_requirements_mapped',['R14'],'PASS' if not missing else 'ERROR','Every requirement has an executed or explicitly blocked check.',observed=missing,
                        next_action='' if not missing else 'Implement missing requirement checks before claiming completeness.')
        counts,verdict,code=summarize_checks(self.checks)
        requirements={}
        for r,title in REQUIREMENTS.items():
            related=[c for c in self.checks if r in c['requirements']]
            status=summarize_checks(related)[1] if related else 'NOT_EVALUATED'
            requirements[r]={'title':title,'status':status,'check_ids':[c['id'] for c in related]}
        artifacts=[c for c in self.checks if c.get('category')=='artifact']
        engineering=[c for c in self.checks if c.get('category') in ['numerical','geometry','physical']]
        failed=[c for c in self.checks if c['status'] in ['ERROR','FAIL']];blocked=[c for c in self.checks if c['status']=='BLOCKED']
        action='REPAIR_TEST_EXECUTION' if not self.functional else 'REVISE_FAILED_DESIGN_OR_ARTIFACTS' if failed else 'COMPLETE_PHYSICAL_QUALIFICATION' if blocked else 'ALL_RECORDED_GATES_PASS'
        source_files=['config/design.json','requirement.md','scripts/run_ci.py','scripts/ci_support.py']+[p.relative_to(self.root).as_posix() for p in sorted((self.root/'tests').glob('test_*.py'))]
        data={'schema':'beam-wall-mount-ci-v1','version':'v1','run_id':self.run_id,'mode':self.mode,'completed_at':now(),
              'test_system_functional':self.functional,'unit_tests_run':self.unit_count,'engineering_release':verdict if self.mode!='selftest' else 'NOT_EVALUATED',
              'artifact_complete':self.mode!='selftest' and bool(artifacts) and all(c['status']=='PASS' for c in artifacts),
              'numerical_screen_pass':all(c['status']=='PASS' for c in self.checks if c.get('category')=='numerical') and any(c.get('category')=='numerical' for c in self.checks),
              'physical_qualification_pass':all(c['status']=='PASS' for c in self.checks if c.get('category')=='physical') and any(c.get('category')=='physical' for c in self.checks),
              'project_complete':self.mode!='selftest' and verdict=='PASS','exit_code':code,'counts':counts,'log_file':self.log_relative,
              'log_sha256_pending':True,'tool_versions':self.versions,'stages':self.stages,'checks':self.checks,'requirements':requirements,
              'input_hashes':{p:sha256(self.root/p) for p in source_files if (self.root/p).is_file()},
              'executed_source_hashes':self.executed_sources,
              'next_iteration':{'action':action,'priorities':[{'check_id':c['id'],'status':c['status'],'requirement_ids':c['requirements'],'message':c['message'],'next_action':c.get('next_action'),'evidence':c.get('evidence',[])} for c in failed+blocked]},
              'hosted_ci_execution':'NOT_RUN_NO_REPOSITORY_REQUESTED','notes':['Local CI commands were executed. Hosted GitHub Actions execution is not claimed.','Test-system functionality is separate from engineering acceptance.','Reconstructed v1 results never reuse historical v0 values as new evidence.']}
        self.log.write('\nFINAL '+json.dumps({'test_system_functional':self.functional,'engineering_release':data['engineering_release'],'counts':counts,'exit_code':code})+'\n');self.log.close()
        data.pop('log_sha256_pending');data['log_sha256']=sha256(self.root/self.log_relative)
        summary_path=self.root/'results'/('selftest_summary.json' if self.mode=='selftest' else 'ci_summary.json')
        summary_path.write_text(json.dumps(data,indent=2)+'\n')
        if self.mode!='selftest':
            lines=['# Next iteration feedback','',f'Run: {self.run_id}',f'Engineering release: **{verdict}**',f'Test system functional: **{self.functional}**',f'Counts: {counts}',f'Full log: `{self.log_relative}`','',
                   'A passing test harness does not override failed geometry, analysis or physical evidence.','', '## Required actions','']
            for c in failed+blocked:
                lines += [f"### {c['id']}",'',f"Status: **{c['status']}**; requirements: {', '.join(c['requirements'])}.",c['message'],
                          'Observed: `'+json.dumps(c.get('observed'),ensure_ascii=False)+'`','Criterion: `'+json.dumps(c.get('criterion'),ensure_ascii=False)+'`',
                          '**Next action:** '+c.get('next_action','Review the recorded evidence.'),'Evidence: '+', '.join('`'+x+'`' for x in c.get('evidence',[])),'']
            if not failed and not blocked:lines+=['All recorded checks pass. Preserve evidence and document any new scope separately.']
            (self.root/'results/next_iteration.md').write_text('\n'.join(lines)+'\n')
            (self.root/'results/requirement_matrix.md').write_text('# Requirement verification matrix\n\n| ID | Requirement | Status |\n| --- | --- | --- |\n'+''.join(f'| {r} | {v["title"]} | {v["status"]} |\n' for r,v in requirements.items()))
        print(json.dumps({k:data[k] for k in ['run_id','mode','test_system_functional','unit_tests_run','engineering_release','artifact_complete','project_complete','counts','exit_code','log_file']},indent=2))
        return code

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=DEFAULT_ROOT);ap.add_argument('--mode',choices=['audit','full','selftest'],default='audit');args=ap.parse_args()
    ci=CI(args.root,args.mode)
    ci.guarded('dependencies',ci.dependencies);ci.guarded('unit_tests',ci.units)
    if args.mode!='selftest':
        native_python=os.environ.get('FREECAD_PYTHON','/usr/bin/python3')
        ci.guarded('native_cad',lambda:ci.computational_stage('native_cad',[native_python,'scripts/build_cad.py','--root',str(ci.root),'--validate-only'],'results/freecad_validation.json',['R11']))
        ci.guarded('calculations',lambda:ci.computational_stage('calculations',[sys.executable,'scripts/calculate.py','--root',str(ci.root)],'results/calculations.json',['R05','R08','R14']))
        ci.guarded('geometric_fit',lambda:ci.computational_stage('geometric_fit',[sys.executable,'scripts/check_geometric_fit.py','--root',str(ci.root)],'results/geometric_fit.json',['R02','R03','R04','R15']))
        ci.guarded('fem',lambda:ci.computational_stage('fem',[sys.executable,'scripts/run_fem.py','--root',str(ci.root),'--force' if args.mode=='full' else '--audit'],'results/fem_summary.json' if args.mode=='full' else 'results/fem_audit.json',['R05','R10','R12','R13']))
        if args.mode=='full':
            ci.guarded('fem_figure',lambda:ci.computational_stage('fem_figure',[sys.executable,'scripts/render_fem.py','--root',str(ci.root)],'results/fem_render.json',['R10']))
        ci.guarded('artifacts',ci.artifacts);ci.guarded('physical',ci.physical)
    return ci.finish()

if __name__=='__main__':raise SystemExit(main())
