#!/usr/bin/env python3
"""Real Gmsh -> C3D10 CalculiX pipeline with retained compressed solver evidence.

--force executes all configured meshes/cases. --audit validates saved input/output
hashes without claiming a fresh solve. Optional --part/--size/--cases is explicitly
partial development mode. No simulation fills physical acceptance records.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, lzma, math, os, re, shutil, subprocess, sys, tempfile, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if (ROOT.parent/'.v1_runtime').exists():sys.path.append(str(ROOT.parent/'.v1_runtime'))
import numpy as np
CASE_NAMES=['fx','fy','fz','tx','my','mz']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def byte_sha(b):return hashlib.sha256(b).hexdigest()
def save_json(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,indent=2)+'\n')
def xzwrite(p,b):Path(p).write_bytes(lzma.compress(b,preset=6))
def read_raw(p):p=Path(p);return lzma.decompress(p.read_bytes()) if p.suffix=='.xz' else p.read_bytes()
def relative(p,r):return Path(p).relative_to(r).as_posix()
def check(cid,req,ok,message,observed=None,criterion=None,evidence=None,action=None):
    return {'id':cid,'requirements':list(req),'status':ok if isinstance(ok,str) else ('PASS' if ok else 'FAIL'),'message':message,'observed':observed,'criterion':criterion,'evidence':evidence or ['results/fem_summary.json'],'next_action':action or ('Retain this validated numerical evidence; physical qualification remains separate.' if ok is True else 'Investigate this result, revise the model/mesh or restore the missing evidence and rerun. Do not weaken the acceptance threshold.')}
def vm(s):
    s=np.asarray(s,dtype=float);return np.sqrt(np.maximum(0,((s[:,0]-s[:,1])**2+(s[:,1]-s[:,2])**2+(s[:,2]-s[:,0])**2)/2+3*np.sum(s[:,3:6]**2,axis=1)))
def spectral(s):
    s=np.asarray(s,dtype=float);m=np.zeros((len(s),3,3));m[:,0,0]=s[:,0];m[:,1,1]=s[:,1];m[:,2,2]=s[:,2];m[:,0,1]=m[:,1,0]=s[:,3];m[:,1,2]=m[:,2,1]=s[:,4];m[:,0,2]=m[:,2,0]=s[:,5]
    return np.max(np.abs(np.linalg.eigvalsh(m)),axis=1)
def direction_bound(values):
    a=np.asarray(values);assert a.shape[0]==6
    return np.sqrt(np.sum(a[:3]**2,axis=0))+a[3]+np.sqrt(np.sum(a[4:6]**2,axis=0))
FLOAT=re.compile(r'[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][+-]?\d+)?')
def parse_frd(data):
    if isinstance(data,bytes):data=data.decode('ascii',errors='replace')
    current=None;fields={};ids={}
    for line in data.splitlines():
        if line.startswith(' -4'):
            parts=line.split();current=parts[1] if len(parts)>1 else None
            if current in ('DISP','STRESS','FORC'):fields[current]=[];ids[current]=[]
        elif line.startswith(' -3'):current=None
        elif current in fields and line.startswith(' -1'):
            nid=int(line[3:13]);vals=[float(x.replace('D','E')) for x in FLOAT.findall(line[13:])];n=6 if current=='STRESS' else 3
            if len(vals)<n:raise ValueError('Malformed FRD result row')
            ids[current].append(nid);fields[current].append(vals[:n])
    for name in ('DISP','STRESS','FORC'):
        if not fields.get(name):raise ValueError('Missing required FRD field '+name)
    return {n:(np.asarray(ids[n],dtype=np.int64),np.asarray(fields[n],dtype=float)) for n in fields}
def parse_dat_stress(data):
    if isinstance(data,bytes):data=data.decode('ascii',errors='replace')
    active=False;keys=[];vals=[]
    for line in data.splitlines():
        if 'stresses (elem' in line.lower():active=True;continue
        if not active:continue
        w=line.split()
        if len(w)==8:
            try:
                e,ip=int(w[0]),int(w[1]);s=[float(x.replace('D','E')) for x in w[2:]]
            except ValueError:continue
            keys.append((e,ip));vals.append([s[0],s[1],s[2],s[3],s[5],s[4]])
    if not vals:raise ValueError('No integration-point stress records in DAT')
    return np.asarray(keys,dtype=np.int64),np.asarray(vals,dtype=float)
def solver_finished(log,returncode):
    return returncode==0 and 'Job finished' in log and not any(x in log.lower() for x in ['*error','segmentation fault','nan detected'])
def set_lines(name,nodes):
    arr=[int(x) for x in nodes];return '*NSET,NSET='+name+'\n'+'\n'.join(','.join(map(str,arr[i:i+16])) for i in range(0,len(arr),16))+'\n'
def clipped_triangle_load_weights(points,bounds):
    """Integrate T6 shape functions over triangle intersection with an XY rectangle."""
    points=np.asarray(points,float);poly=[p.copy() for p in points]
    for axis,limit,sign in [(0,bounds[0],1),(0,bounds[1],-1),(1,bounds[2],1),(1,bounds[3],-1)]:
        new=[]
        if not poly:break
        previous=poly[-1];prev_in=sign*(previous[axis]-limit)>=-1e-10
        for current in poly:
            cur_in=sign*(current[axis]-limit)>=-1e-10
            if cur_in!=prev_in:
                fraction=(limit-previous[axis])/(current[axis]-previous[axis]);new.append(previous+fraction*(current-previous))
            if cur_in:new.append(current)
            previous=current;prev_in=cur_in
        poly=new
    weights=np.zeros(6);area=0.
    if len(poly)<3:return weights,area
    mat=np.vstack([points.T,np.ones(3)]);inv=np.linalg.inv(mat)
    for i in range(1,len(poly)-1):
        sub=np.asarray([poly[0],poly[i],poly[i+1]]);a=abs(np.linalg.det(np.column_stack([sub[1]-sub[0],sub[2]-sub[0]])))/2
        if a<1e-14:continue
        area+=a
        for q in [(2/3,1/6,1/6),(1/6,2/3,1/6),(1/6,1/6,2/3)]:
            point=np.asarray(q)@sub;L=inv@np.r_[point,1];N=np.r_[L*(2*L-1),4*L[0]*L[1],4*L[1]*L[2],4*L[2]*L[0]];weights+=a/3*N
    return weights,area
def gmsh_mesh(root,part,h,cfg):
    import gmsh
    source=root/'cad'/('bracket_structural_core_only.step' if part=='bracket' else 'beam_400mm.step');label=f'{part}_h{h:g}'.replace('.','p');dest=root/'mesh';dest.mkdir(exist_ok=True)
    gmsh.initialize();gmsh.option.setNumber('General.Terminal',0);gmsh.logger.start()
    try:
        gmsh.model.add(label);vols=gmsh.model.occ.importShapes(str(source));gmsh.model.occ.synchronize();vols=gmsh.model.getEntities(3)
        if len(vols)!=1:raise ValueError(f'Expected one {part} solid, got {len(vols)}')
        cad_volume=sum(gmsh.model.occ.getMass(d,t) for d,t in vols)
        bb=np.asarray(gmsh.model.getBoundingBox(3,vols[0][1]));patch_tags=[]
        if part=='beam':
            # Derive the swept tetrahedral mesh from the actual delivered STEP end face.
            # Its exact section is retained; the mesher varies axial layer length with h.
            left=float(bb[0]);length=cfg['beam']['length_mm'];ends=[]
            for _,tag in gmsh.model.getEntities(2):
                box=gmsh.model.getBoundingBox(2,tag)
                if abs(box[0]-left)<1e-5 and abs(box[3]-left)<1e-5:ends.append((2,tag))
            if len(ends)!=1:raise ValueError('Could not identify the exact STEP end section')
            copied=gmsh.model.occ.copy(ends);gmsh.model.occ.remove(vols,recursive=True)
            gmsh.model.occ.extrude(copied,length,0,0,numElements=[math.ceil(length/h)],recombine=False)
            gmsh.model.occ.synchronize();vols=gmsh.model.getEntities(3)
            if len(vols)!=1:raise ValueError('Swept STEP section must create one identical solid')
            if abs(gmsh.model.occ.getMass(*vols[0])-cad_volume)/cad_volume>1e-9:raise ValueError('Swept geometry differs from the supplied STEP solid')
        gmsh.option.setNumber('Mesh.MeshSizeMin',min(1.0,h*.3));gmsh.option.setNumber('Mesh.MeshSizeMax',h/2 if part=='beam' else h)
        gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',0 if part=='beam' else 12);gmsh.option.setNumber('Mesh.MinimumCirclePoints',16)
        gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',1);gmsh.option.setNumber('Mesh.Algorithm3D',1)
        gmsh.option.setNumber('Mesh.ElementOrder',1);gmsh.option.setNumber('Mesh.Optimize',1);print('  Gmsh volume mesh generation',flush=True);gmsh.model.mesh.generate(3);print('  Gmsh quadratic conversion',flush=True)
        # C3D10 displacement interpolation. Straight-sided thin tube geometry avoids
        # midside inversion; curved bracket surfaces retain quadratic geometry.
        gmsh.option.setNumber('Mesh.SecondOrderLinear',1 if part=='beam' else 0);gmsh.model.mesh.setOrder(2)
        if part=='bracket':gmsh.model.mesh.optimize('HighOrder',force=False,niter=1)
        et,ets,conn=gmsh.model.mesh.getElements(3)
        if len(et)!=1 or int(et[0])!=11:raise ValueError('Volume mesh is not exclusively tetra10')
        elem_ids=np.asarray(ets[0],dtype=np.int64);tet=np.asarray(conn[0],dtype=np.int64).reshape(-1,10)
        nt,co,_=gmsh.model.mesh.getNodes();nt=np.asarray(nt,dtype=np.int64);co=np.asarray(co).reshape(-1,3)
        used=np.unique(tet);ni={int(n):i for i,n in enumerate(nt)};xyz=np.asarray([co[ni[int(n)]] for n in used]);lookup={int(n):i for i,n in enumerate(used)}
        ccx=tet[:,[0,1,2,3,4,5,6,7,9,8]]
        jac=np.asarray(gmsh.model.mesh.getElementQualities(elem_ids,'minDetJac'))
        if not np.all(np.isfinite(jac)) or jac.min()<=0:raise ValueError(f'Invalid minimum Jacobian {jac.min()}')
        loc,weights=gmsh.model.mesh.getIntegrationPoints(11,'Gauss4');_,dets,gcoords=gmsh.model.mesh.getJacobians(11,loc)
        weights=np.asarray(weights);dets=np.asarray(dets).reshape(-1,len(weights));gc=np.asarray(gcoords).reshape(-1,len(weights),3)
        dv=dets*weights;fevolume=float(np.sum(dv));centroid=np.sum(gc*dv[:,:,None],axis=(0,1))/fevolume
        triangles=[]
        for _,tag in gmsh.model.getEntities(2):
            typ,_,nodes=gmsh.model.mesh.getElements(2,tag)
            for t,ns in zip(typ,nodes):
                if int(t)==9:
                    for aa,bb2,cc,ab,bc,ca in np.asarray(ns).reshape(-1,6):triangles.extend([(aa,ab,ca),(ab,bb2,bc),(ca,bc,cc),(ab,bc,ca)])
                elif int(t)==2:triangles.extend(np.asarray(ns).reshape(-1,3).tolist())
        tri=np.asarray([[lookup[int(n)] for n in t] for t in triangles],dtype=np.int32)
        patch_forces={};patch_area=0.
        if part=='beam':
            top=cfg['beam']['outer_mm']/2;mid=(xyz[:,0].min()+xyz[:,0].max())/2
            for _,tag in gmsh.model.getEntities(2):
                box=gmsh.model.getBoundingBox(2,tag)
                if abs(box[2]-top)>1e-5 or abs(box[5]-top)>1e-5:continue
                typ,_,nodes=gmsh.model.mesh.getElements(2,tag)
                for t,ns in zip(typ,nodes):
                    if int(t)!=9:raise ValueError('Load patch requires quadratic triangle faces')
                    for row in np.asarray(ns).reshape(-1,6):
                        pts=np.asarray([xyz[lookup[int(n)]][:2] for n in row[:3]])
                        weights,area=clipped_triangle_load_weights(pts,(mid-5,mid+5,-5,5))
                        patch_area+=area
                        for nid,w in zip(row,weights):patch_forces[int(nid)]=patch_forces.get(int(nid),0.)-cfg['loads']['service_force_N']*w/100.
            patch_forces={n:f for n,f in patch_forces.items() if abs(f)>1e-13}
            if abs(patch_area-100)>1e-5:raise ValueError('Integrated central surface patch area is not100mm2')
        meshpath=dest/(label+'.msh');gmsh.option.setNumber('Mesh.MshFileVersion',4.1);gmsh.option.setNumber('Mesh.Binary',0);gmsh.write(str(meshpath));raw=meshpath.read_bytes();xzwrite(str(meshpath)+'.xz',raw);meshpath.unlink()
        meta={'part':part,'label':label,'size_mm':h,'nodes':len(used),'elements':len(tet),'element_type':'C3D10','gmsh_version':gmsh.__version__,'geometry_order':1 if part=='beam' else 2,'meshing_method':'STEP end-face sweep with triangular base split into tetrahedra' if part=='beam' else 'OCC unstructured curved quadratic tetrahedra','minimum_det_jacobian':float(jac.min()),'FE_volume_mm3':fevolume,'CAD_volume_mm3':float(cad_volume),'volume_relative_error':abs(fevolume-cad_volume)/cad_volume,'FE_centroid_mm':centroid.tolist(),'load_patch_area_mm2':patch_area if part=='beam' else None,'source_step':relative(source,root),'source_step_sha256':sha(source),'design_sha256':sha(root/'config/design.json'),'gmsh_to_ccx_nodes':'1,2,3,4,5,6,7,8,10,9; swaps the last two midside nodes','surface_triangles':len(tri)}
        save_json(dest/(label+'.json'),meta);(dest/(label+'.gmsh.log')).write_text('\n'.join(gmsh.logger.get())+'\n')
        return {'meta':meta,'node_ids':used,'xyz':xyz,'elements':ccx,'element_ids':elem_ids,'triangles':tri,'patch_forces':patch_forces}
    finally:
        gmsh.logger.stop();gmsh.finalize()
def boundary_sets(mesh,cfg):
    xyz=mesh['xyz'];ids=mesh['node_ids'];part=mesh['meta']['part'];p=cfg['bracket'];eps=2e-4
    if part=='bracket':
        radial=np.minimum(np.hypot(xyz[:,1],xyz[:,2]-p['bolt_pitch_mm']/2),np.hypot(xyz[:,1],xyz[:,2]+p['bolt_pitch_mm']/2))
        bores=np.abs(radial-p['bolt_bore_mm']/2)<eps
        washer_radius=cfg['anchors'].get('washer_od_min_mm',cfg['anchors']['washer_od_mm'])/2
        annulus=(radial>=p['bolt_bore_mm']/2-eps)&(radial<=washer_radius+eps)&((abs(xyz[:,0])<eps)|(abs(xyz[:,0]-p['plate_thickness_mm'])<eps))
        fixed_x=ids[annulus];fixed_y=ids[bores];fixed_z=ids[bores]
    else:
        ends=(abs(xyz[:,0]-xyz[:,0].min())<eps)|(abs(xyz[:,0]-xyz[:,0].max())<eps)
        fixed_y=ids[ends];fixed_z=ids[ends];left=np.where(abs(xyz[:,0]-xyz[:,0].min())<eps)[0];fixed_x=np.asarray([ids[left[np.argmin(np.linalg.norm(xyz[left,1:],axis=1))]]])
    if min(len(fixed_x),len(fixed_y),len(fixed_z))==0:raise ValueError('Empty support node set')
    return [fixed_x,fixed_y,fixed_z]
def common_deck(mesh,cfg,bc):
    part=mesh['meta']['part'];mat=cfg[part];lines=['*HEADING','Reconstructed beam wall mount v1; actual '+part+' C3D10 model','*NODE,NSET=NALL']
    lines.extend(f'{int(n)},'+','.join(f'{v:.12g}' for v in x) for n,x in zip(mesh['node_ids'],mesh['xyz']))
    lines+=['*ELEMENT,TYPE=C3D10,ELSET=EALL'];lines.extend(f'{int(e)},'+','.join(str(int(n)) for n in t) for e,t in zip(mesh['element_ids'],mesh['elements']))
    lines+=['*MATERIAL,NAME=MAT','*ELASTIC',f"{mat['E_MPa']:.12g},{mat['nu']:.12g}",'*DENSITY',f"{mat['density_kg_m3']*1e-12:.12g}",'*SOLID SECTION,ELSET=EALL,MATERIAL=MAT']
    for j,ns in enumerate(bc):lines.append(set_lines('FIX'+str(j+1),ns).rstrip())
    lines+=['*BOUNDARY','FIX1,1,1','FIX2,2,2','FIX3,3,3']
    return ('\n'.join(lines)+'\n').encode()
def balanced_tip_load(mesh,cfg,case):
    xyz=mesh['xyz'];ids=mesh['node_ids'];tip=xyz[:,0].max();which=np.where(abs(xyz[:,0]-tip)<1e-4)[0]
    if len(which)<4:raise ValueError('Insufficient tip nodes to apply balanced resultants')
    rr=xyz[which]-np.asarray([tip,0,0]);A=np.zeros((6,3*len(rr)))
    for i,(x,y,z) in enumerate(rr):
        A[:3,3*i:3*i+3]=np.eye(3);A[3:,3*i:3*i+3]=[[0,-z,y],[z,0,-x],[-y,x,0]]
    target=np.zeros(6);idx=CASE_NAMES.index(case);target[idx]=(cfg['loads']['bracket_force_envelope_N'] if idx<3 else cfg['loads']['bracket_torsion_envelope_Nmm'] if idx==3 else cfg['loads']['bracket_transverse_moment_envelope_Nmm'])
    fs=(A.T@np.linalg.solve(A@A.T,target)).reshape(-1,3)
    if np.max(abs(A@fs.ravel()-target))>1e-8:raise ValueError('Unbalanced applied tip resultant')
    return [(int(ids[ii]),j+1,float(v)) for ii,ff in zip(which,fs) for j,v in enumerate(ff) if abs(v)>1e-13]
def case_deck(mesh,cfg,case):
    part=mesh['meta']['part'];cload=balanced_tip_load(mesh,cfg,case) if part=='bracket' else [(n,3,f) for n,f in mesh['patch_forces'].items()]
    lines=['*INCLUDE,INPUT=common_mesh.inc','*STEP','*STATIC','*CLOAD']+[f'{n},{d},{f:.12g}' for n,d,f in cload]
    if part=='beam':lines+=['*DLOAD',f"EALL,GRAV,{cfg['loads']['gravity_m_s2']*1000:.12g},0,0,-1"]
    lines+=['*NODE FILE','U,RF','*EL FILE','S','*EL PRINT,ELSET=EALL','S','*END STEP']
    return ('\n'.join(lines)+'\n').encode(),cload

def consistent_gravity_nodes(mesh,cfg):
    """Exact constant body-force vector for straight-sided tetra10 geometry.
    Integral(Ncorner)=-V/20 and Integral(Nedge)=V/5. CalculiX RF is
    external nodal force = reaction + CLOAD + DLOAD, so subtract these
    applied loads on constrained degrees of freedom to recover reactions.
    """
    ids=mesh['node_ids'];xyz=mesh['xyz'];lookup={int(n):i for i,n in enumerate(ids)}
    ix=np.asarray([[lookup[int(n)] for n in e] for e in mesh['elements']],dtype=int);pts=xyz[ix[:,:4]]
    volumes=abs(np.linalg.det(np.stack([pts[:,1]-pts[:,0],pts[:,2]-pts[:,0],pts[:,3]-pts[:,0]],axis=2)))/6
    if not math.isclose(float(volumes.sum()),mesh['meta']['FE_volume_mm3'],rel_tol=1e-9):raise ValueError('Straight tetrahedral gravity volume inconsistent with mesh quadrature')
    weights=np.asarray([-.05]*4+[.2]*6);nodal=np.zeros((len(ids),3));fg=-volumes*cfg['beam']['density_kg_m3']*1e-9*cfg['loads']['gravity_m_s2']
    for j,w in enumerate(weights):np.add.at(nodal[:,2],ix[:,j],fg*w)
    return nodal
def execute_case(root,mesh,cfg,case,common,bc,solver):
    label=mesh['meta']['label'];folder=root/'fem'/label;folder.mkdir(parents=True,exist_ok=True);inp,loads=case_deck(mesh,cfg,case);base=folder/case
    t0=time.monotonic();env=os.environ.copy();env.update({'OMP_NUM_THREADS':'1','CCX_NPROC_STIFFNESS':'1','CCX_NPROC_RESULTS':'1','OPENBLAS_NUM_THREADS':'1'})
    with tempfile.TemporaryDirectory(prefix='ccx_'+case+'_',dir=root.parent) as tmp:
        tmp=Path(tmp);(tmp/'common_mesh.inc').write_bytes(common);(tmp/(case+'.inp')).write_bytes(inp)
        proc=subprocess.run([str(solver),'-i',case],cwd=tmp,env=env,capture_output=True,text=True,timeout=600)
        log=proc.stdout+'\n'+proc.stderr;logpath=base.with_suffix('.solver.log');logpath.write_text(log)
        xzwrite(base.with_suffix('.inp.xz'),inp)
        if not solver_finished(log,proc.returncode):raise RuntimeError(f'CalculiX {label}/{case} failed (exit{proc.returncode}); see {relative(logpath,root)}')
        frd=(tmp/(case+'.frd')).read_bytes();dat=(tmp/(case+'.dat')).read_bytes();fields=parse_frd(frd);ipids,ips=parse_dat_stress(dat)
        xzwrite(base.with_suffix('.frd.xz'),frd);xzwrite(base.with_suffix('.dat.xz'),dat)
    expected=mesh['node_ids'];ordered={}
    for name,(ids,a) in fields.items():
        ix=np.argsort(ids);ids=ids[ix];a=a[ix]
        if not np.array_equal(ids,expected):raise ValueError('FRD node coverage differs from volume mesh for '+name)
        ordered[name]=a
    xyz=mesh['xyz'];lookup={int(n):i for i,n in enumerate(expected)};forces=np.zeros((len(xyz),3))
    for n,d,f in loads:forces[lookup[n],d-1]+=f
    applied=forces.sum(axis=0);moment=np.cross(xyz,forces).sum(axis=0)
    if mesh['meta']['part']=='beam':
        grav=np.asarray([0,0,-cfg['beam']['density_kg_m3']*mesh['meta']['FE_volume_mm3']*1e-9*cfg['loads']['gravity_m_s2']]);applied+=grav;moment+=np.cross(mesh['meta']['FE_centroid_mm'],grav)
    applied_nodes=forces+(consistent_gravity_nodes(mesh,cfg) if mesh['meta']['part']=='beam' else 0)
    reaction=np.zeros_like(forces);raw_rf_support=np.zeros_like(forces)
    for d,ns in enumerate(bc):
        ii=[lookup[int(n)] for n in ns];raw_rf_support[ii,d]=ordered['FORC'][ii,d];reaction[ii,d]=ordered['FORC'][ii,d]-applied_nodes[ii,d]
    rs=reaction.sum(axis=0);rm=np.cross(xyz,reaction).sum(axis=0)
    force_scale=max(np.linalg.norm(applied),cfg['loads']['bracket_force_envelope_N'] if mesh['meta']['part']=='bracket' else cfg['loads']['service_force_N']);moment_scale=max(np.linalg.norm(moment),cfg['loads']['bracket_torsion_envelope_Nmm'] if mesh['meta']['part']=='bracket' else cfg['loads']['service_force_N']*cfg['beam']['length_mm']/2)
    metrics={'case':case,'solver_version':re.search(r'Version\s+([0-9.]+)',log).group(1) if re.search(r'Version\s+([0-9.]+)',log) else 'unknown','returncode':proc.returncode,'finished':True,'elapsed_seconds':time.monotonic()-t0,'max_nodal_vm_MPa':float(vm(ordered['STRESS']).max()),'max_IP_vm_MPa':float(vm(ips).max()),'max_displacement_mm':float(np.linalg.norm(ordered['DISP'],axis=1).max()),'force_balance_relative':float(np.linalg.norm(applied+rs)/force_scale),'moment_balance_relative':float(np.linalg.norm(moment+rm)/moment_scale),'applied_force_N':applied.tolist(),'reaction_force_N':rs.tolist(),'RF_support_external_force_N':raw_rf_support.sum(axis=0).tolist(),'reaction_extraction':'CalculiX RF is reaction plus applied nodal loads. Subtract consistent CLOAD and C3D10 GRAV vectors at constrained DOFs.','applied_moment_Nmm':moment.tolist(),'reaction_moment_Nmm':rm.tolist(),'input_decompressed_sha256':byte_sha(inp),'common_include_decompressed_sha256':byte_sha(common),'frd_decompressed_sha256':byte_sha(frd),'dat_decompressed_sha256':byte_sha(dat),'integration_points':len(ips)}
    save_json(base.with_suffix('.json'),metrics)
    return {'metrics':metrics,'stress':ordered['STRESS'],'u':ordered['DISP'],'ipstress':ips,'ipids':ipids}
def compile_level(root,mesh,cfg,cases):
    part=mesh['meta']['part'];metrics=dict(mesh['meta']);metrics['cases']=[c['metrics'] for c in cases];xyz=mesh['xyz'];tri=mesh['triangles'];surface_ids=np.unique(tri);smap={int(x):i for i,x in enumerate(surface_ids)}
    compact_tri=np.asarray([[smap[int(n)] for n in row] for row in tri],dtype=np.int32)
    if part=='bracket':
        if len(cases)!=6:return metrics,None
        if any(not np.array_equal(cases[0]['ipids'],c['ipids']) for c in cases[1:]):raise ValueError('Integration-point result identifiers differ between load cases')
        nv=direction_bound([vm(c['stress']) for c in cases]);npb=direction_bound([spectral(c['stress']) for c in cases]);iv=direction_bound([vm(c['ipstress']) for c in cases]);ipb=direction_bound([spectral(c['ipstress']) for c in cases]);ub=direction_bound([np.linalg.norm(c['u'],axis=1) for c in cases])
        metrics.update({'max_vm_bound_MPa':float(max(nv.max(),iv.max())),'max_principal_abs_bound_MPa':float(max(npb.max(),ipb.max())),'max_nodal_vm_bound_MPa':float(nv.max()),'max_IP_vm_bound_MPa':float(iv.max()),'max_nodal_principal_bound_MPa':float(npb.max()),'max_IP_principal_bound_MPa':float(ipb.max()),'max_displacement_bound_mm':float(ub.max())})
        surface={'part':part,'xyz':xyz[surface_ids].tolist(),'triangles':compact_tri.tolist(),'vm':nv[surface_ids].tolist(),'principal':npb[surface_ids].tolist(),'metrics':metrics}
    else:
        c=cases[0];nv=vm(c['stress']);mid=(xyz[:,0].min()+xyz[:,0].max())/2;which=(abs(xyz[:,0]-mid)<=mesh['meta']['size_mm']/2)&(abs(xyz[:,2])<=2)&(abs(xyz[:,1])>=.4*cfg['beam']['outer_mm'])
        if not np.any(which):raise ValueError('No neutral sidewall nodes for global beam displacement comparison')
        metrics.update({'max_nodal_vm_MPa':float(nv.max()),'max_IP_vm_MPa':float(vm(c['ipstress']).max()),'max_displacement_mm':float(np.linalg.norm(c['u'],axis=1).max()),'section_mean_uz_mm':float(np.mean(c['u'][which,2])),'section_node_count':int(which.sum()),'section_sampling':'abs(x-midspan)<=h/2, abs(z)<=2mm, abs(y)>=0.4*OD; retains local maximum separately'})
        surface={'part':part,'xyz':xyz[surface_ids].tolist(),'triangles':compact_tri.tolist(),'vm':nv[surface_ids].tolist(),'metrics':metrics}
    save_json(root/'fem'/mesh['meta']['label']/'summary.json',metrics)
    return metrics,surface

def generate_stl(root,cfg):
    import gmsh
    files=[];inputs={'config/design.json':sha(root/'config/design.json'),'scripts/run_fem.py':sha(__file__)}
    sources=[root/'cad/bracket.step']+sorted((root/'cad').glob('fit_coupon_*.step'))
    for source in sources:
        dest=root/'mesh'/(source.stem+'.stl');gmsh.initialize();gmsh.option.setNumber('General.Terminal',0);gmsh.logger.start()
        try:
            gmsh.model.add(source.stem);gmsh.model.occ.importShapes(str(source));gmsh.model.occ.synchronize();gmsh.option.setNumber('Mesh.MeshSizeMin',.10);gmsh.option.setNumber('Mesh.MeshSizeMax',2);gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',20);gmsh.option.setNumber('Mesh.ElementOrder',1);gmsh.model.mesh.generate(2)
            typ,tags,nodes=gmsh.model.mesh.getElements(2);tri=[]
            for t,ns in zip(typ,nodes):
                if int(t)!=2:raise ValueError('Printable STL surface contains non-triangles')
                tri.extend(np.asarray(ns).reshape(-1,3).tolist())
            tri=np.asarray(tri,dtype=np.int64);edges=np.sort(np.vstack([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1);_,counts=np.unique(edges,axis=0,return_counts=True)
            if np.any(counts!=2):raise ValueError('STL surface is not watertight/manifold')
            gmsh.option.setNumber('Mesh.Binary',1);gmsh.write(str(dest));logpath=dest.with_suffix('.gmsh.log');logpath.write_text('\n'.join(gmsh.logger.get())+'\n')
            inputs[relative(source,root)]=sha(source);files.append({'path':relative(dest,root),'sha256':sha(dest),'source':relative(source,root),'triangles':len(tri),'manifold':True,'generator':'Gmsh '+gmsh.__version__,'bytes':dest.stat().st_size})
        finally:gmsh.logger.stop();gmsh.finalize()
    out={'schema':'gmsh-stl-manifest-v1','generator':'Gmsh','version':gmsh.__version__,'input_hashes':inputs,'files':files,'checks':[check('stl:gmsh_generated',['R12'],len(files)==6,'Six printable STL files generated by Gmsh from current STEP sources',len(files),6,[f['path'] for f in files])]+[check('stl:manifold:'+Path(f['path']).stem,['R12'],f['manifold'],'Every mesh edge belongs to two triangles',True,'closed manifold',[f['path']]) for f in files]}
    save_json(root/'mesh/stl_manifest.json',out);return out

def numerical_checks(root,cfg,levels,stl):
    out=list(stl.get('checks',[]));acc=cfg['acceptance'];sf=cfg['loads']['material_safety_factor']
    for level in levels:
        label=level['label'];evidence=['mesh/'+label+'.json','fem/'+label+'/summary.json']
        out.append(check('fem:positive_jacobian:'+label,['R13'],level['minimum_det_jacobian']>0,'Adaptive minimum element determinant is positive',level['minimum_det_jacobian'],'>0',evidence))
        if level['part']=='beam':out.append(check('fem:beam_volume:'+label,['R05','R13'],level['volume_relative_error']<=acc['beam_volume_relative_error'],'Actual FE geometry volume versus exact CAD',level['volume_relative_error'],acc['beam_volume_relative_error'],evidence,'Refine the curved-profile geometric discretization while preserving positive Jacobians; do not replace FE mass with CAD mass to hide a volume error.'))
        for case in level.get('cases',[]):
            jobev=['fem/'+label+'/'+case['case']+'.solver.log','fem/'+label+'/'+case['case']+'.json','fem/'+label+'/'+case['case']+'.inp.xz','fem/'+label+'/common_mesh.inc.xz']
            if level['size_mm']==min(cfg['mesh'][level['part']+'_sizes_mm']):jobev+=['fem/'+label+'/'+case['case']+'.frd.xz','fem/'+label+'/'+case['case']+'.dat.xz']
            else:jobev+=['fem/retained_evidence.json']
            out.append(check('fem:solved:'+label+':'+case['case'],['R13'],case['finished'] and case['returncode']==0,'CalculiX actual solve finished',{'exit':case['returncode'],'finished':case['finished']},'exit0 and Job finished',jobev))
            for key in ['force_balance_relative','moment_balance_relative']:
                out.append(check('fem:'+key+':'+label+':'+case['case'],['R05','R13'],case[key]<=acc['reaction_relative_error'],'Applied resultant and constrained-DOF reaction equilibrium',case[key],acc['reaction_relative_error'],jobev,'Review applied loads, support degrees of freedom, units, actual FE gravity mass and solver results before relying on stress output.'))
    for part in ['bracket','beam']:
        ordered=sorted([x for x in levels if x['part']==part],key=lambda x:x['size_mm'],reverse=True)
        if len(ordered)<2:out.append(check('fem:mesh_coverage:'+part,['R05','R13'],'ERROR','At least two complete mesh levels are required',len(ordered),'>=2',action='Run all configured mesh levels; a partial development run is not an engineering acceptance run.'));continue
        coarse,fine=ordered[-2:]
        fields=['max_vm_bound_MPa','max_principal_abs_bound_MPa','max_displacement_bound_mm'] if part=='bracket' else ['max_nodal_vm_MPa','max_IP_vm_MPa','max_displacement_mm']
        for k in fields:
            lim=acc['displacement_convergence_relative'] if 'displacement' in k else acc['stress_convergence_relative'];change=abs(fine[k]-coarse[k])/max(abs(fine[k]),1e-30)
            out.append(check('fem:convergence:'+part+':'+k,['R05','R13'],change<=lim,'Last two configured mesh levels compared without excluding peak nodes or integration points',{'coarse':coarse[k],'fine':fine[k],'relative_change':change},lim,action='Review peak location, idealized attachment/contact and geometric discretization; refine or revise the actual model and rerun. A below-allowable stress cannot override failed peak-stress convergence.'))
        allowable=cfg[part]['strength_reference_MPa']/sf if part=='bracket' else cfg[part]['yield_reference_MPa']/sf
        stressfields=fields[:2]
        for k in stressfields:out.append(check('fem:strength:'+part+':'+k,['R05'],fine[k]<=allowable,'Finest-model material stress screen; physical material qualification is separate',fine[k],allowable))
        u=fine[fields[-1]];out.append(check('fem:displacement:'+part,['R05'],u<=acc['max_displacement_mm'],'Finest-model displacement screen excludes real joint clearance take-up and creep',u,acc['max_displacement_mm']))
        if part=='beam':
            sys.path.insert(0,str(root/'scripts'));from calculate import calculate
            analytical=calculate(cfg)['values']['beam_nominal_euler_deflection_mm'];difference=abs(abs(fine['section_mean_uz_mm'])-analytical)/analytical
            out.append(check('fem:Euler_comparison',['R05','R08','R13'],difference<=acc['beam_theory_relative_error'],'Comparable section-average vertical deflection versus nominal Euler theory; local maximum reported separately',{'FEM_section_mm':abs(fine['section_mean_uz_mm']),'Euler_mm':analytical,'relative_difference':difference,'nodes':fine['section_node_count']},acc['beam_theory_relative_error']))
    return out

def render_surfaces(root,surfaces,summary):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.colors import Normalize
    import plotly.graph_objects as go
    failures=[c for c in summary['checks'] if c['status']=='FAIL']
    traces=[];titles=[]
    for part in ['bracket','beam']:
        s=surfaces[part];xyz=np.asarray(s['xyz']);tri=np.asarray(s['triangles']);vals=np.asarray(s['vm']);met=s['metrics'];fields=['vm','principal'] if part=='bracket' else ['vm']
        fig=plt.figure(figsize=(13,7 if part=='bracket' else 5));fig.suptitle(('Bracket conservative stress bounds' if part=='bracket' else 'Beam stress under 10 N central patch and gravity'),fontsize=17,fontweight='bold')
        pf=[x for x in failures if part in x['id']]
        subtitle=('Numerical verification FAIL: '+', '.join(x['id'].split(':')[-1] for x in pf)) if pf else 'Displayed model screens pass; manufactured assembly qualification remains BLOCKED'
        fig.text(.04,.90,subtitle,fontsize=9,color='#a13613' if pf else '#334455')
        for k,field in enumerate(fields):
            ax=fig.add_subplot(1,len(fields),k+1,projection='3d');value=np.asarray(s[field]);norm=Normalize(0,float(value.max()));pc=Poly3DCollection(xyz[tri],facecolors=plt.get_cmap('viridis')(norm(value[tri].mean(axis=1))),linewidths=0,rasterized=True);ax.add_collection3d(pc)
            lo=xyz.min(axis=0);hi=xyz.max(axis=0);ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_zlim(lo[2],hi[2]);ax.set_box_aspect(np.maximum(hi-lo,.1));ax.view_init(elev=17,azim=-55 if part=='bracket' else -65);ax.set_axis_off();ax.set_title('Von Mises bound' if field=='vm' and part=='bracket' else 'Absolute principal bound' if field=='principal' else 'Von Mises stress')
            fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),ax=ax,shrink=.6,pad=.01,label='MPa')
            raw=met['max_vm_bound_MPa'] if part=='bracket' and field=='vm' else met['max_principal_abs_bound_MPa'] if field=='principal' else max(met['max_nodal_vm_MPa'],met['max_IP_vm_MPa'])
            ax.text2D(.02,.02,f'Raw node/IP peak {raw:.6g} MPa',transform=ax.transAxes,fontsize=10)
            title=part.title()+' '+field;traces.append(go.Mesh3d(x=xyz[:,0],y=xyz[:,1],z=xyz[:,2],i=tri[:,0],j=tri[:,1],k=tri[:,2],intensity=value,colorscale='Viridis',cmin=0,cmax=float(value.max()),colorbar={'title':'MPa'},visible=len(traces)==0,flatshading=False,name=title,hovertemplate='%{intensity:.5g} MPa<extra>'+title+'</extra>'));titles.append(title)
        fig.text(.04,.03,'Actual CalculiX nodal fields on undeformed geometry. Triangle colors use nodal means; raw peaks are retained.\nBracket bounds combine six independent linear cases. Isotropic material and engaged restraints do not qualify physical contact.',fontsize=8,color='#334455');fig.savefig(root/'results'/f'{part}_stress.png',dpi=170,bbox_inches='tight');plt.close(fig)
    figure=go.Figure(traces);buttons=[{'label':t,'method':'update','args':[{'visible':[i==j for i in range(len(traces))]},{'title':t}]} for j,t in enumerate(titles)]
    figure.update_layout(title=titles[0],scene={'aspectmode':'data','xaxis_title':'x mm','yaxis_title':'y mm','zaxis_title':'z mm'},updatemenus=[{'buttons':buttons,'x':0,'y':1.15}],margin={'l':0,'r':0,'b':0,'t':70},height=700)
    notices=''.join('<li>'+c['id']+': '+str(c.get('observed'))+'</li>' for c in failures)
    html='<!doctype html><html><head><meta charset="utf-8"><title>v1 solved stress viewer</title></head><body style="font-family:system-ui;margin:24px"><h1>Reconstructed v1 stress results</h1><p>Real Gmsh / CalculiX outputs. Physical fit, print, wall and installation qualification remain BLOCKED.</p><h2>Numerical failures</h2><ul>'+notices+'</ul><p>Bracket fields are conservative arbitrary-direction bounds, not a single physical tensor state. Beam case is central vertical 10 N patch plus gravity. No external scripts or network are needed.</p>'+figure.to_html(full_html=False,include_plotlyjs=True)+'</body></html>'
    (root/'results/stress_viewer.html').write_text(html)

def retain_finest_fields(root,levels):
    """Keep complete fine fields; retain all coarse inputs/logs/metrics and raw hashes."""
    finest={part:min(x['size_mm'] for x in levels if x['part']==part) for part in ['bracket','beam']};omitted=[];retained=[]
    for level in levels:
        full=level['size_mm']==finest[level['part']]
        for c in level['cases']:
            for ext in ['frd','dat']:
                p=root/'fem'/level['label']/(c['case']+'.'+ext+'.xz')
                entry={'path':relative(p,root),'compressed_sha256':sha(p),'compressed_bytes':p.stat().st_size,'uncompressed_sha256':c[ext+'_decompressed_sha256'],'level':level['label'],'case':c['case']}
                if full:retained.append(entry)
                else:omitted.append(entry);p.unlink()
    out={'schema':'solver-field-retention-v1','policy':'Complete raw FRD/DAT fields retained for finest bracket and beam. Coarse raw fields were genuinely solved and parsed, then omitted as regenerable output to keep the self-contained download manageable. All coarse input decks, meshes, successful solver logs, per-case summaries, mesh quality, reactions, envelope metrics and exact omitted-file hashes remain. --force regenerates all levels.','audit_scope':'Full-field reparse for finest meshes; hash-protected cached coarse metrics and executed solver logs for refinement history.','omitted_regenerable_fields':omitted,'retained_full_fields':retained}
    save_json(root/'fem/retained_evidence.json',out);return out

def collect_artifacts(root):
    out={}
    for folder in ['mesh','fem']:
        for p in (root/folder).rglob('*'):
            if p.is_file():out[relative(p,root)]=sha(p)
    for n in ['results/bracket_stress.png','results/beam_stress.png','results/stress_viewer.html','results/stress_surface_data.json.xz']:
        if (root/n).is_file():out[n]=sha(root/n)
    return out

def audit(root):
    path=root/'results/fem_summary.json'
    if not path.is_file():return {'execution_complete':False,'checks':[check('fem:audit_missing',['R13'],'ERROR','No saved FEM summary exists',action='Run scripts/run_fem.py --force to generate genuine solver evidence.')],'actual_solver_runs':0},3
    saved=json.loads(path.read_text());checks=[];mismatch=[]
    for kind in ['input_hashes','artifact_hashes']:
        for rel,h in saved.get(kind,{}).items():
            p=root/rel
            if not p.is_file() or sha(p)!=h:mismatch.append(rel)
    checks.append(check('fem:audit_hashes',['R10','R12','R13','R14'],not mismatch,'FEM input and output bytes match the executed-run provenance',mismatch,'no missing or changed files',action='Restore evidence or rerun the changed model. Stale results cannot be accepted as current.'))
    cfg=json.loads((root/'config/design.json').read_text());canonical_levels=[];canonical_errors=[];recomputed=[]
    if not mismatch:
        try:
            for part in ['bracket','beam']:
                for h in cfg['mesh'][part+'_sizes_mm']:
                    label=f'{part}_h{h:g}'.replace('.','p');level=json.loads((root/'fem'/label/'summary.json').read_text());assert level['label']==label and level['part']==part and level['size_mm']==h;expected=CASE_NAMES if part=='bracket' else ['central_gravity'];assert [c['case'] for c in level['cases']]==expected;canonical_levels.append(level)
            assert canonical_levels==saved.get('levels'), 'Top-level levels differ from hash-protected per-level evidence'
            stl=json.loads((root/'mesh/stl_manifest.json').read_text());recomputed=numerical_checks(root,cfg,canonical_levels,stl)
            prior={c['id']:c for c in saved['checks']}
            for c in recomputed:assert c==prior.get(c['id']), 'Saved check differs from recomputation: '+c['id']
        except Exception as e:canonical_errors.append(str(e))
    checks.append(check('fem:audit_recomputed_checks',['R05','R13','R14'],not mismatch and not canonical_errors,'Top-level metrics and checks match protected per-level evidence and fresh acceptance calculations',canonical_errors,'no altered metric/status and all configured levels',action='Restore altered summaries or rerun the model. Recorded PASS labels cannot override recomputed metrics.'))
    errors=list(canonical_errors);case_count=0;full_count=0;cached_count=0;fine_cases={};retention_path=root/'fem/retained_evidence.json'
    retention=json.loads(retention_path.read_text()) if retention_path.is_file() else {};omitted={x['path']:x for x in retention.get('omitted_regenerable_fields',[])}
    if not mismatch:
        for level in canonical_levels:
            arrays=[]
            for c in level.get('cases',[]):
                case_count+=1;base=root/'fem'/level['label']/c['case']
                try:
                    inp=read_raw(base.with_suffix('.inp.xz'));common=read_raw(base.parent/'common_mesh.inc.xz')
                    assert byte_sha(inp)==c['input_decompressed_sha256'];assert byte_sha(common)==c['common_include_decompressed_sha256'];assert solver_finished(base.with_suffix('.solver.log').read_text(),c['returncode'])
                    fp=base.with_suffix('.frd.xz');dp=base.with_suffix('.dat.xz')
                    if fp.is_file() and dp.is_file():
                        frd=read_raw(fp);dat=read_raw(dp);fields=parse_frd(frd);ipids,stress=parse_dat_stress(dat)
                        assert byte_sha(frd)==c['frd_decompressed_sha256'];assert byte_sha(dat)==c['dat_decompressed_sha256']
                        assert math.isclose(float(vm(fields['STRESS'][1]).max()),c['max_nodal_vm_MPa'],rel_tol=1e-10,abs_tol=1e-10)
                        assert math.isclose(float(vm(stress).max()),c['max_IP_vm_MPa'],rel_tol=1e-10,abs_tol=1e-10)
                        arrays.append((fields,stress));full_count+=1
                    else:
                        for pp,ext in [(fp,'frd'),(dp,'dat')]:assert omitted[relative(pp,root)]['uncompressed_sha256']==c[ext+'_decompressed_sha256']
                        cached_count+=1
                except Exception as e:errors.append(level['label']+'/'+c['case']+': '+repr(e))
            if arrays:
                try:
                    if level['part']=='bracket':
                        assert len(arrays)==6
                        for kind,fun in [('vm',vm),('principal_abs',spectral)]:
                            n=direction_bound([fun(f['STRESS'][1]) for f,ip in arrays]);i=direction_bound([fun(ip) for f,ip in arrays]);observed=float(max(n.max(),i.max()));assert math.isclose(observed,level['max_'+kind+'_bound_MPa'],rel_tol=1e-10,abs_tol=1e-10)
                        u=direction_bound([np.linalg.norm(f['DISP'][1],axis=1) for f,ip in arrays]);assert math.isclose(float(u.max()),level['max_displacement_bound_mm'],rel_tol=1e-10,abs_tol=1e-10)
                    else:assert math.isclose(float(np.linalg.norm(arrays[0][0]['DISP'][1],axis=1).max()),level['max_displacement_mm'],rel_tol=1e-10,abs_tol=1e-10)
                except Exception as e:errors.append(level['label']+' reconstructed fine-field envelope: '+repr(e))
    good=not mismatch and not errors and saved.get('execution_complete') is True and case_count==saved.get('actual_solver_runs') and full_count==7
    checks.append(check('fem:audit_evidence',['R13','R14'],good,'Every case input/log verified; finest FRD/DAT fields reparsed and envelope peaks recomputed; coarse metrics use explicitly retained cached evidence',{'errors':errors,'cases_verified':case_count,'full_field_cases_reparsed':full_count,'coarse_cases_with_cached_metrics':cached_count},'all configured cases; 7 finest full-field cases',action='Repair corrupted/incomplete evidence or execute --force. Coarse cached metrics are not represented as freshly reparsed raw fields.'))
    out={'schema':'fem-audit-v1','execution_complete':good,'audit_only':True,'solver_runs_this_invocation':0,'actual_solver_runs':case_count,'checks':checks+recomputed,'input_hashes':saved.get('input_hashes',{}),'artifact_hashes':saved.get('artifact_hashes',{}),'retention_policy':retention.get('policy')}
    save_json(root/'results/fem_audit.json',out)
    return out,3 if not good else (1 if any(c['status']=='FAIL' for c in out['checks']) else 0)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);m=ap.add_mutually_exclusive_group();m.add_argument('--force',action='store_true');m.add_argument('--audit',action='store_true');ap.add_argument('--part',choices=['beam','bracket']);ap.add_argument('--size',type=float);ap.add_argument('--cases',nargs='+',choices=CASE_NAMES);ap.add_argument('--skip-stl',action='store_true');args=ap.parse_args();root=args.root.resolve()
    if args.audit:
        out,code=audit(root);print(json.dumps({'mode':'audit','execution_complete':out['execution_complete'],'checks':len(out['checks']),'FAIL':sum(c['status']=='FAIL' for c in out['checks']),'exit_code':code}));return code
    cfg=json.loads((root/'config/design.json').read_text());partial=bool(args.part or args.size or args.cases or args.skip_stl);levels=[];surfaces={};actual=0;t0=time.monotonic();out={'schema':'executed-fem-v1','version':'v1','reconstructed':True,'partial_development_run':partial,'execution_complete':False,'actual_solver_runs':0,'checks':[]}
    try:
        import cad_ccx,gmsh
        solver=Path(os.environ['CCX']) if os.environ.get('CCX') else cad_ccx.executable()
        stl=generate_stl(root,cfg) if not args.skip_stl else {'checks':[]}
        parts=[args.part] if args.part else ['bracket','beam']
        for part in parts:
            sizes=[args.size] if args.size else cfg['mesh'][part+'_sizes_mm']
            for h in sizes:
                print(f'MESH {part} h={h}',flush=True);mesh=gmsh_mesh(root,part,h,cfg);bc=boundary_sets(mesh,cfg);common=common_deck(mesh,cfg,bc);folder=root/'fem'/mesh['meta']['label'];folder.mkdir(parents=True,exist_ok=True);xzwrite(folder/'common_mesh.inc.xz',common)
                names=(args.cases or CASE_NAMES) if part=='bracket' else ['central_gravity'];print(f'SOLVE {mesh["meta"]["label"]}: {mesh["meta"]["nodes"]} nodes {mesh["meta"]["elements"]} elements; cases {names}',flush=True)
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    fs=[pool.submit(execute_case,root,mesh,cfg,n,common,bc,solver) for n in names];cases=[]
                    for n,f in zip(names,fs):
                        result=f.result();cases.append(result);actual+=1;print(f'FINISHED {mesh["meta"]["label"]}/{n}: {result["metrics"]["elapsed_seconds"]:.1f}s',flush=True)
                metric,surface=compile_level(root,mesh,cfg,cases);levels.append(metric)
                if surface is not None:surfaces[part]=surface
        out.update({'execution_complete':not partial,'actual_solver_runs':actual,'solver_runs_this_invocation':actual,'elapsed_seconds':time.monotonic()-t0,'software':{'Gmsh':gmsh.__version__,'CalculiX':cad_ccx.version(),'Python':sys.version.split()[0]},'levels':levels,'model_limits':['Structural core-only bracket; fit ribs and interference preload excluded.','Isotropic PETG and zero-clearance engaged supports are screening idealizations.','X restraints act at x0 and7.8 on r9.3..14.35mm annuli, using the minimum specified retention-washer OD28.7mm. Y/Z fixed on sleeve bores.','Actual nominal0.2mm washer gap, contact opening, friction and preload are not solved.','Beam quadratic displacement uses straight-sided swept geometry from the actual STEP endface. Consistent nodal traction integrates the clipped central100mm2 pressure patch exactly, even where the mesh crosses the patch boundary.','Six independent bracket cases use conservative direction bounds via triangle and Cauchy-Schwarz inequalities.','Physical acceptance remains BLOCKED without measured evidence.']})
        if not partial:
            out['checks']=numerical_checks(root,cfg,levels,stl);out['checks'].append(check('fem:executed_all_cases',['R13'],actual==len(cfg['mesh']['bracket_sizes_mm'])*6+len(cfg['mesh']['beam_sizes_mm']),'All configured solver cases genuinely executed',actual,20));render_surfaces(root,surfaces,out);xzwrite(root/'results/stress_surface_data.json.xz',json.dumps(surfaces,separators=(',',':')).encode());retention=retain_finest_fields(root,levels);out['raw_retention_policy']=retention['policy'];out['checks'].append(check('fem:3d_visuals',['R10'],True,'Actual solved stress fields rendered to two PNGs and self-contained interactive HTML',3,3,['results/bracket_stress.png','results/beam_stress.png','results/stress_viewer.html']))
        else:out['checks']=[check('fem:partial_run',['R13'],'BLOCKED','This is a development subset, not a complete FEM acceptance run',actual,'all configured cases',action='Execute scripts/run_fem.py --force without development filters.')]
        inputs=['config/design.json','scripts/run_fem.py','scripts/calculate.py','cad/bracket_structural_core_only.step','cad/beam_400mm.step']
        out['input_hashes']={p:sha(root/p) for p in inputs};out['input_hashes'].update(stl.get('input_hashes',{}));out['artifact_hashes']=collect_artifacts(root);save_json(root/'results/fem_summary.json',out)
        code=2 if partial else 1 if any(c['status']=='FAIL' for c in out['checks']) else 0
    except Exception as e:
        out.update({'execution_complete':False,'actual_solver_runs':actual,'levels':levels,'error':repr(e),'traceback':traceback.format_exc(),'checks':[check('fem:execution_error',['R10','R12','R13'],'ERROR',str(e),action='Inspect solver/mesher logs and repair the actual execution error; no engineering pass can be issued.')]});save_json(root/'results/fem_summary.json',out);print(traceback.format_exc());code=3
    print(json.dumps({'stage':'FEM','execution_complete':out['execution_complete'],'actual_solver_runs':actual,'checks':len(out['checks']),'FAIL':sum(c['status']=='FAIL' for c in out['checks']),'exit_code':code}),flush=True);return code
if __name__=='__main__':raise SystemExit(main())
