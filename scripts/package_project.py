#!/usr/bin/env python3
"""Create a self-contained frozen version archive and verify every static byte.

Run --freeze --manifest-only, run the final CI audit, then --freeze to create ZIP.
Mutable execution logs and latest summaries carry their own source hashes.
"""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MUTABLE={'MANIFEST.sha256','results/ci_summary.json','results/next_iteration.md','results/requirement_matrix.md','results/selftest_summary.json'}
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and not any(x in p.parts for x in ['__pycache__','.venv','.git']) and p.suffix not in ['.pyc','.FCBak'])
def static(root):
    return [p for p in files(root) if p.relative_to(root).as_posix() not in MUTABLE and p.relative_to(root).parts[0]!='logs'
            and not (p.relative_to(root).parts[0]=='results' and p.suffix in ['.json','.md','.txt'] and p.name!='fem_summary.json')]
def verify(root):
    hashes={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (root/'MANIFEST.sha256').read_text().splitlines() if line}
    issues=[]
    for name,wanted in hashes.items():
        p=(root/name).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file() or digest(p)!=wanted:issues.append(name)
    expected=set(hashes);actual={p.relative_to(root).as_posix() for p in static(root)}
    issues += ['Unmanifested static file: '+n for n in sorted(actual-expected)]
    print(json.dumps({'files_checked':len(hashes),'manifest_pass':not issues,'issues':issues},indent=2))
    return not issues
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--freeze',action='store_true');ap.add_argument('--manifest-only',action='store_true');ap.add_argument('--verify',action='store_true');ap.add_argument('--output',type=Path);a=ap.parse_args();root=a.root.resolve()
    if a.verify:return 0 if verify(root) else 1
    if not a.freeze:ap.error('Choose --freeze or --verify')
    expected=(root/'frozen_requirements.sha256').read_text().split()[0]
    if digest(root/'requirement.md')!=expected:raise RuntimeError('Frozen requirements changed. Create a documented new baseline before packaging.')
    (root/'MANIFEST.sha256').write_text(''.join(digest(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in static(root)))
    if a.manifest_only:
        print(json.dumps({'static_files':len(static(root)),'requirements_frozen':True}));return 0
    if not verify(root):return 1
    out=a.output or root.parent/(root.name+'.zip')
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files(root):z.write(p,root.name+'/'+p.relative_to(root).as_posix())
    with zipfile.ZipFile(out) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('ZIP integrity failed: '+bad)
        entries=len(z.namelist())
    print(json.dumps({'archive':str(out),'files':entries,'bytes':out.stat().st_size,'sha256':digest(out),'zip_crc_pass':True},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
