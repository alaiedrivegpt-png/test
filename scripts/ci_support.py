#!/usr/bin/env python3
"""Small, independently tested CI primitives; no engineering verdict is inferred from a zero process code."""
from __future__ import annotations
import hashlib, json, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {'PASS', 'FAIL', 'BLOCKED', 'ERROR'}

def now():
    return datetime.now(timezone.utc).isoformat()

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def project_path(root, name):
    root=Path(root).resolve(); p=(root/name).resolve()
    if not p.is_relative_to(root):
        raise ValueError('Evidence path escapes project: '+str(name))
    return p

def check(identifier, requirements, status, message, *, category='artifact', observed=None, criterion=None, next_action='', evidence=None):
    if status not in STATUSES: raise ValueError('Unknown check status: '+status)
    return dict(id=identifier, requirements=list(requirements), category=category, status=status,
                message=message, observed=observed, criterion=criterion, next_action=next_action,
                evidence=list(evidence or []))

def audit_hashes(root, expected):
    problems=[]
    if not isinstance(expected,dict) or not expected: return ['No provenance hashes recorded.']
    for name,wanted in expected.items():
        try:
            p=project_path(root,name)
            if not p.is_file(): problems.append('Missing: '+name)
            elif not isinstance(wanted,str) or sha256(p)!=wanted: problems.append('Changed: '+name)
        except (OSError,ValueError) as exc: problems.append(str(exc))
    return problems

def result_revision(path):
    p=Path(path)
    return (p.stat().st_mtime_ns,p.stat().st_size) if p.is_file() else None

def require_fresh_result(path, before):
    after=result_revision(path)
    if after is None:raise ValueError('Required result file was not produced: '+str(path))
    if after==before:raise ValueError('Stage did not refresh its result file: '+str(path))
    return after

def run_command(command, root, log, *, env=None, timeout=1800):
    started=now(); timer=time.monotonic()
    log.write('\n=== COMMAND '+json.dumps(command)+' ===\nSTART '+started+'\n');log.flush()
    error=None
    try:
        result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=timeout)
        stdout,stderr,code=result.stdout,result.stderr,result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout=exc.stdout or '';stderr=exc.stderr or '';code=124;error='Command timed out.'
        if isinstance(stdout,bytes):stdout=stdout.decode(errors='replace')
        if isinstance(stderr,bytes):stderr=stderr.decode(errors='replace')
    except OSError as exc:
        stdout='';stderr=str(exc);code=127;error='Command could not be executed.'
    log.write('STDOUT\n'+stdout+'\nSTDERR\n'+stderr+'\n')
    elapsed=time.monotonic()-timer
    log.write(f'END {now()} EXIT {code} DURATION_SECONDS {elapsed:.6f}\n');log.flush()
    return dict(command=command,started_at=started,finished_at=now(),duration_s=elapsed,
                returncode=code,execution_error=error,stdout=stdout,stderr=stderr)

def summarize_checks(checks):
    counts={k:sum(c['status']==k for c in checks) for k in ['PASS','FAIL','BLOCKED','ERROR']}
    verdict='ERROR' if counts['ERROR'] else 'FAIL' if counts['FAIL'] else 'BLOCKED' if counts['BLOCKED'] else 'PASS'
    code={'PASS':0,'FAIL':1,'BLOCKED':2,'ERROR':3}[verdict]
    return counts,verdict,code

def read_result(root, relative, required_requirements):
    p=project_path(root,relative)
    data=json.loads(p.read_text())
    checks=data.get('checks')
    if not isinstance(checks,list) or not checks: raise ValueError(relative+': no check results')
    seen=set(); coverage=set()
    for c in checks:
        if not isinstance(c,dict) or not c.get('id') or c.get('status') not in STATUSES:
            raise ValueError(relative+': malformed check')
        if c['id'] in seen: raise ValueError(relative+': duplicate check ID '+c['id'])
        seen.add(c['id'])
        if not isinstance(c.get('requirements'),list) or not c['requirements']:
            raise ValueError(relative+': unmapped check '+c['id'])
        coverage.update(c['requirements'])
        if c['status']!='PASS' and not c.get('next_action'):
            raise ValueError(relative+': non-pass check lacks next action '+c['id'])
    missing=set(required_requirements)-coverage
    if missing: raise ValueError(relative+': missing requirement coverage '+str(sorted(missing)))
    issues=audit_hashes(root,data.get('input_hashes',{}))
    if 'config/design.json' not in data.get('input_hashes',{}): issues.append('Design configuration not bound by hash.')
    if data.get('artifact_hashes'): issues+=audit_hashes(root,data['artifact_hashes'])
    if issues: raise ValueError(relative+': stale/incomplete provenance: '+'; '.join(issues))
    if data.get('execution_complete') is not True: raise ValueError(relative+': execution_complete is not true')
    return data

def validate_record(root, record):
    if record is None: return 'BLOCKED','No physical evidence has been entered.'
    if not isinstance(record,dict): return 'ERROR','Physical evidence must be a structured record.'
    if record.get('status') not in ['PASS','FAIL','BLOCKED']: return 'ERROR','Physical status is missing or invalid.'
    if record['status']!='PASS': return record['status'],record.get('note','Physical qualification has not passed.')
    paths=record.get('evidence_files',[])
    if not record.get('operator') or not record.get('date') or not paths:
        return 'BLOCKED','A claimed physical pass lacks operator, date or evidence.'
    if not all(project_path(root,x).is_file() for x in paths): return 'ERROR','Physical evidence file is missing.'
    return 'PASS','Recorded physical evidence is present; human review is still responsible for its authenticity.'
