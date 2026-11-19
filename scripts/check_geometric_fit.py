#!/usr/bin/env python3
"""Independent CadQuery/Open CASCADE fit audit of delivered v1 STEP solids.

No FreeCAD builder functions are imported. Native STEP solids are read by
CadQuery and checked with OCCT BRepCheck_Analyzer, BRepAlgoAPI_Common/Cut and
BRepExtrema_DistShapeShape. A hypothetical catalogue-tolerance part is labeled
separately from the delivered nominal CAD. Physical press-fit retention cannot
be approved by geometry alone.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys,traceback
from datetime import datetime,timezone
from importlib.metadata import version
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def record(id,requirements,status,message,observed=None,criterion=None,next_action='',evidence=None):
    return dict(id=id,requirements=requirements,status=status,message=message,observed=observed,criterion=criterion,next_action=next_action,evidence=evidence or [])
def engines():
    import cadquery as cq
    import OCP
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common,BRepAlgoAPI_Cut
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    return cq,OCP,BRepAlgoAPI_Common,BRepAlgoAPI_Cut,BRepCheck_Analyzer,BRepExtrema_DistShapeShape

def common_shape(a,b):
    cq,_,Common,_,_,_=engines();op=Common(a.wrapped,b.wrapped);op.Build()
    if not op.IsDone():raise RuntimeError('Open CASCADE common Boolean did not finish')
    return cq.Shape.cast(op.Shape())
def cut_shape(a,b):
    cq,_,_,Cut,_,_=engines();op=Cut(a.wrapped,b.wrapped);op.Build()
    if not op.IsDone():raise RuntimeError('Open CASCADE cut Boolean did not finish')
    return cq.Shape.cast(op.Shape())
def distance(a,b):
    *_,Distance=engines();op=Distance(a.wrapped,b.wrapped);op.Perform()
    if not op.IsDone():raise RuntimeError('Open CASCADE distance calculation did not finish')
    return op.Value()
def volume(shape):return sum(s.Volume() for s in shape.Solids())
def bounds(shape):
    b=shape.BoundingBox();return {k:getattr(b,k) for k in ['xmin','xmax','ymin','ymax','zmin','zmax']}
def solid_check(shape,expected_solids=1):
    _,_,_,_,Analyzer,_=engines()
    if shape is None or shape.wrapped.IsNull():return False,{'null':True}
    from OCP.BRepCheck import BRepCheck_Shell,BRepCheck_NoError
    ss=shape.Solids();valid=bool(Analyzer(shape.wrapped,True).IsValid())
    # TopoDS_Solid.Closed is an optional cached flag, not a shell-closure test.
    closed=bool(ss) and all(s.Shells() and all(BRepCheck_Shell(sh.wrapped).Closed()==BRepCheck_NoError for sh in s.Shells()) for s in ss)
    data={'valid':valid,'closed':closed,'solids':len(ss),'volume_mm3':volume(shape),'bbox_mm':bounds(shape)}
    return valid and closed and len(ss)==expected_solids and data['volume_mm3']>0,data

def collision_check(core,tube,id='fit:core_collision',requirements=None,tolerance_mm3=0.001):
    overlap=common_shape(core,tube);v=volume(overlap);d=distance(core,tube)
    return record(id,requirements or ['R03','R15'],'PASS' if v<=tolerance_mm3 else 'FAIL',
      'Structural-core collision checked by OCCT Boolean common on imported solids.',
      {'intersection_volume_mm3':v,'minimum_distance_mm':d,'intersection_bbox_mm':bounds(overlap) if v>tolerance_mm3 else None},
      {'maximum_prohibited_intersection_mm3':tolerance_mm3},
      'Correct the plug, root fillet or assembly pose; regenerate CAD and rerun both-end fit checks before manufacturing.',
      ['cad/beam_400mm.step','cad/bracket_structural_core_only.step'])

def pose_check(actual,expected,id='fit:pose',tolerance_mm3=0.001):
    v=volume(actual)+volume(expected)-2*volume(common_shape(actual,expected))
    return record(id,['R03','R15'],'PASS' if abs(v)<=tolerance_mm3 else 'FAIL',
      'Actual delivered assembly instance agrees with the required transform.',
      {'symmetric_difference_volume_mm3':v,'actual_bbox_mm':bounds(actual)},
      {'maximum_symmetric_difference_mm3':tolerance_mm3},
      'Repair the misplaced or mirrored instance and regenerate the assembly STEP.', ['cad/assembly.step'])

def hardware_pose_check(shape,kind,cfg):
    """Check every modeled hardware instance against independent assembly coordinates."""
    a=cfg['anchors'];p=cfg['bracket'];wall=cfg['assembly']['right_wall_x_mm'];tol=cfg['acceptance']['dimension_tolerance_mm']
    if kind=='sleeves':start=0.;length=a['sleeve_length_mm']
    elif kind=='retention_washers':start=a['sleeve_length_mm'];length=a['washer_thickness_mm']
    elif kind=='anchor_shanks_simplified':start=-a['embedment_mm'];length=a['embedment_mm']+a['sleeve_length_mm']+a['washer_thickness_mm']
    else:raise ValueError('Unknown hardware kind '+kind)
    center=start+length/2
    expected=sorted((x,0.,z) for x in [center,wall-center] for z in [-p['bolt_pitch_mm']/2,p['bolt_pitch_mm']/2])
    actual=sorted(tuple(q.Center().toTuple()) for q in shape.Solids())
    lengths=[bounds(q)['xmax']-bounds(q)['xmin'] for q in shape.Solids()]
    # Floating STEP centers may differ at 1e-13 mm; lexicographic sorting would
    # then swap the two z positions. Exhaust all 4! one-to-one assignments.
    import itertools
    position_error=min((max(math.dist(x,y) for x,y in zip(actual,pose))
                        for pose in itertools.permutations(expected)),default=float('inf')) if len(actual)==4 else float('inf')
    good=len(actual)==4 and position_error<=tol and all(abs(x-length)<=tol for x in lengths)
    return record('hardware:positions:'+kind,['R04','R15'],'PASS' if good else 'FAIL',
      'Every imported modeled hardware instance has the required axial length, bolt center and left/right pose.',
      {'actual_centers_mm':actual,'axial_lengths_mm':lengths,'maximum_position_error_mm':position_error},
      {'expected_centers_mm':expected,'axial_length_mm':length,'dimension_tolerance_mm':tol},
      'Repair misplaced sleeves, washers or simplified shanks and regenerate both component and assembly STEP files.',
      ['cad/'+kind+'.step','cad/assembly.step'])

def cylinders(shape):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    result=[]
    for face in shape.Faces():
        a=BRepAdaptor_Surface(face.wrapped)
        if a.GetType()==GeomAbs_Cylinder:
            c=a.Cylinder();loc=c.Location();d=c.Axis().Direction()
            result.append({'radius_mm':c.Radius(),'location_mm':[loc.X(),loc.Y(),loc.Z()],'axis':[d.X(),d.Y(),d.Z()]})
    return result

def rounded_tube(outer,inner,ro,ri,length,x):
    cq,*_=engines()
    a=cq.Workplane('YZ',origin=(x,0,0)).rect(outer,outer).extrude(length).edges('|X').fillet(ro).val()
    b=cq.Workplane('YZ',origin=(x-1,0,0)).rect(inner,inner).extrude(length+2).edges('|X').fillet(ri).val()
    return cut_shape(a,b)

def run(root):
    root=Path(root);cfg=json.loads((root/'config/design.json').read_text());manifest=json.loads((root/'cad/geometry_manifest.json').read_text());b=cfg['beam'];c=cfg['bracket'];a=cfg['anchors'];asm=cfg['assembly'];tol=cfg['acceptance']['geometry_volume_tolerance_mm3'];dtol=cfg['acceptance']['dimension_tolerance_mm']
    cq,OCP,*_=engines();checks=[];inputs=['config/design.json','cad/geometry_manifest.json','scripts/check_geometric_fit.py']
    names=['beam_400mm','bracket','bracket_structural_core_only','bracket_added_ribs','bracket_right','bracket_right_structural_core_only','sleeves','retention_washers','anchor_shanks_simplified','assembly']
    shapes={}
    for name in names:
        p='cad/'+name+'.step';inputs.append(p)
        if not (root/p).is_file():raise FileNotFoundError('Missing delivered STEP solid: '+p)
        shapes[name]=cq.importers.importStep(str(root/p)).val()
        expected=manifest['assembly'] if name=='assembly' else manifest['geometry'][name]
        good,measured=solid_check(shapes[name],expected['solids'])
        good=good and abs(measured['volume_mm3']-expected['volume_mm3'])<=tol
        checks.append(record('geometry:valid:'+name,['R15'],'PASS' if good else 'FAIL','CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest.',measured,{'expected_solids':expected['solids'],'volume_mm3':expected['volume_mm3'],'volume_tolerance_mm3':tol},'Repair invalid or stale STEP exports and regenerate the manifest.',[p,'cad/geometry_manifest.json']))
    tube=shapes['beam_400mm'];left=shapes['bracket'];right=shapes['bracket_right'];core=shapes['bracket_structural_core_only'];rcore=shapes['bracket_right_structural_core_only'];ribs=shapes['bracket_added_ribs']
    tb=bounds(tube);cb=bounds(core);rb=bounds(rcore)
    actual_dims={'length_mm':tb['xmax']-tb['xmin'],'outside_y_mm':tb['ymax']-tb['ymin'],'outside_z_mm':tb['zmax']-tb['zmin'],'start_x_mm':tb['xmin'],'end_x_mm':tb['xmax']}
    expected_dims={'length_mm':b['length_mm'],'outside_y_mm':b['outer_mm'],'outside_z_mm':b['outer_mm'],'start_x_mm':asm['beam_start_x_mm'],'end_x_mm':asm['beam_end_x_mm']}
    checks.append(record('geometry:beam_dimensions',['R02','R15'],'PASS' if all(abs(actual_dims[k]-v)<=dtol for k,v in expected_dims.items()) else 'FAIL','Beam length, outside section and position measured from delivered STEP.',actual_dims,expected_dims,'Restore the 400 mm tube geometry and its assembly placement.',['cad/beam_400mm.step']))
    radii=sorted(x['radius_mm'] for x in cylinders(tube));expected_r=sorted([b['inner_radius_mm']]*4+[b['outer_radius_mm']]*4)
    face_planes=[]
    for face in tube.Faces():
        if face.geomType()=='PLANE':
            n=face.normalAt();p=face.Center()
            if abs(n.y)>0.999:face_planes.append(abs(p.y))
            elif abs(n.z)>0.999:face_planes.append(abs(p.z))
    flat_levels=sorted(set(round(x,8) for x in face_planes))
    actual_wall=flat_levels[-1]-flat_levels[0] if len(flat_levels)==2 else None
    profile_ok=len(radii)==len(expected_r) and all(abs(x-y)<=dtol for x,y in zip(radii,expected_r)) and actual_wall is not None and abs(actual_wall-b['wall_mm'])<=dtol
    checks.append(record('geometry:catalogue_profile',['R06','R15'],'PASS' if profile_ok else 'FAIL','Actual STEP curved faces and flat walls match the selected rounded catalogue section.',{'cylindrical_radii_mm':radii,'absolute_flat_levels_mm':flat_levels,'flat_wall_mm':actual_wall},{'radii_mm':expected_r,'flat_wall_mm':b['wall_mm']},'Repair the section; do not replace rounded corners by a sharp square.',['cad/beam_400mm.step']))
    expected_right=left.rotate((0,0,0),(0,0,1),180).translate((asm['right_wall_x_mm'],0,0))
    expected_rcore=core.rotate((0,0,0),(0,0,1),180).translate((asm['right_wall_x_mm'],0,0))
    checks.append(pose_check(right,expected_right,'fit:right_printable_pose',tol));checks.append(pose_check(rcore,expected_rcore,'fit:right_core_pose',tol))
    assembly_solids=shapes['assembly'].Solids();matched=[]
    for name in ['beam_400mm','bracket','bracket_right']:
        target=shapes[name];tcenter=target.Center()
        candidates=[s for s in assembly_solids if abs(s.Volume()-volume(target))<=tol and (s.Center()-tcenter).Length<=dtol]
        good=len(candidates)==1 and abs(volume(common_shape(candidates[0],target))-volume(target))<=tol
        checks.append(record('assembly:actual_instance:'+name,['R03','R04','R15'],'PASS' if good else 'FAIL','The assembly STEP contains the actual intended part in its tested pose.',{'matching_solids':len(candidates)},'Exactly one matching solid.','Repair the assembly export; independent component files cannot substitute for a misplaced assembly.',['cad/assembly.step','cad/'+name+'.step']))
    xf=c['plate_thickness_mm']+c['reinforcement_mm'];details={'left_engagement_mm':cb['xmax']-tb['xmin'],'right_engagement_mm':tb['xmax']-rb['xmin'],'left_root_relief_mm':tb['xmin']-xf,'right_root_relief_mm':asm['right_wall_x_mm']-xf-tb['xmax'],'wall_spacing_mm':bounds(right)['xmax']-bounds(left)['xmin']}
    expected={'left_engagement_mm':c['engagement_mm'],'right_engagement_mm':c['engagement_mm'],'left_root_relief_mm':c['root_relief_mm'],'right_root_relief_mm':c['root_relief_mm'],'wall_spacing_mm':asm['right_wall_x_mm']-asm['left_wall_x_mm']}
    checks.append(record('fit:engagement_and_relief',['R03','R04','R15'],'PASS' if all(abs(details[k]-v)<=dtol for k,v in expected.items()) else 'FAIL','Both imported bracket ends seat at the specified engagement and root-relief distances.',details,expected,'Correct tube/plug length or spacing; root fillet must remain outside the inserted tube end.',['cad/bracket_structural_core_only.step','cad/bracket_right_structural_core_only.step','cad/beam_400mm.step']))
    for side,shape in [('left',core),('right',rcore)]:
        item=collision_check(shape,tube,'fit:'+side+':core_collision',tolerance_mm3=tol);checks.append(item)
        d=item['observed']['minimum_distance_mm'];checks.append(record('fit:'+side+':core_clearance',['R03','R15'],'PASS' if item['status']=='PASS' and d+1e-8>=cfg['acceptance']['minimum_core_clearance_mm'] else 'FAIL','Minimum core-to-tube surface clearance measured directly by OCCT.',{'clearance_mm':d},{'minimum_mm':cfg['acceptance']['minimum_core_clearance_mm']},'Increase clearance or adapt plug to measured tube opening; recheck corners and root fillet.',['cad/beam_400mm.step','cad/bracket_structural_core_only.step']))
    actual_added=cut_shape(left,core);difference=volume(cut_shape(actual_added,ribs))+volume(cut_shape(ribs,actual_added))
    checks.append(record('fit:separate_sacrificial_ribs',['R03','R15'],'PASS' if difference<=tol else 'FAIL','Printable-minus-core geometry matches the separately exported rib solids.',{'symmetric_difference_mm3':difference,'rib_volume_mm3':volume(ribs)},{'max_difference_mm3':tol},'Reconcile printable/core/rib exports; do not classify arbitrary collision as allowed press-fit interference.',['cad/bracket.step','cad/bracket_structural_core_only.step','cad/bracket_added_ribs.step']))
    allowed=[];x=c['rib_start_x_mm'];L=c['rib_end_x_mm']-x;h=c['plug_core_mm']/2;outer=c['rib_envelope_mm']/2;half=c['rib_width_mm']/2
    for sign in [-1,1]:
        allowed.append(cq.Solid.makeBox(L,outer-h,2*half,cq.Vector(x,h if sign>0 else -outer,-half)))
        allowed.append(cq.Solid.makeBox(L,2*half,outer-h,cq.Vector(x,-half,h if sign>0 else -outer)))
    rib_mask=cq.Compound.makeCompound(allowed);out_of_mask=volume(cut_shape(ribs,rib_mask))
    checks.append(record('fit:rib_region_bounds',['R03','R15'],'PASS' if out_of_mask<=tol else 'FAIL','Sacrificial ribs lie only in the explicit four thin bands and insertion length.',{'outside_allowed_region_mm3':out_of_mask,'maximum_envelope_mm':c['rib_envelope_mm']},{'max_outside_volume_mm3':tol},'Restrict ribs to the documented sacrificial bands; structural core collision remains prohibited.',['cad/bracket_added_ribs.step','config/design.json']))
    for side,shape,allowed_shape in [('left',left,ribs),('right',right,ribs.rotate((0,0,0),(0,0,1),180).translate((asm['right_wall_x_mm'],0,0)))]:
        common=common_shape(shape,tube);iv=volume(common);prohibited=volume(cut_shape(common,allowed_shape))
        checks.append(record('fit:'+side+':intentional_interference',['R03','R15'],'PASS' if iv>tol and prohibited<=tol else 'FAIL','Nonzero nominal press-fit interference is confined to separately identified sacrificial ribs.',{'total_interference_mm3':iv,'outside_ribs_mm3':prohibited,'maximum_radial_interference_mm':(c['rib_envelope_mm']-b['inner_mm'])/2},{'positive_interference':True,'max_prohibited_volume_mm3':tol},'Correct rib size/location or structural collision; actual insertion force and retention still need physical qualification.',['cad/bracket.step','cad/bracket_added_ribs.step','cad/beam_400mm.step']))
    # Sample translations only: no assertion of frictional fit, deformation, or arbitrary rotations.
    for side,shape,sgn in [('left',core,-1),('right',rcore,1)]:
        samples=[]
        for i in range(int(math.ceil(c['plug_projection_mm']))+1):
            d=min(float(i),c['plug_projection_mm']);moved=shape.translate((sgn*d,0,0));v=volume(common_shape(moved,tube));samples.append({'withdrawal_mm':d,'intersection_mm3':v})
        max_v=max(q['intersection_mm3'] for q in samples)
        checks.append(record('fit:'+side+':sampled_insertion_path',['R03','R15'],'PASS' if max_v<=tol else 'FAIL','Pure axial core insertion/withdrawal sampled at <=1 mm steps from unengaged to seated; physical rib deformation is excluded.',{'maximum_intersection_mm3':max_v,'samples':samples},{'max_prohibited_mm3':tol,'sampling_step_mm':1},'Repair the offending axial position and retest the full path. This sampled path is not a physical insertion-force test.',['cad/bracket_structural_core_only.step','cad/beam_400mm.step']))
    holes=[q for q in cylinders(core) if abs(q['radius_mm']-c['bolt_bore_mm']/2)<=dtol and abs(abs(q['axis'][0])-1)<1e-6]
    hp=sorted(round(q['location_mm'][2],6) for q in holes)
    checks.append(record('hardware:mount_holes',['R04','R15'],'PASS' if hp==[-c['bolt_pitch_mm']/2,c['bolt_pitch_mm']/2] and all(abs(q['location_mm'][1])<=dtol for q in holes) else 'FAIL','Actual cylindrical bores have the required diameter, centerline and pitch.',{'hole_cylinders':holes,'z_centers_mm':hp},{'diameter_mm':c['bolt_bore_mm'],'z_centers_mm':[-c['bolt_pitch_mm']/2,c['bolt_pitch_mm']/2]},'Repair bolt-hole positions and diameters; do not check only config values.',['cad/bracket_structural_core_only.step']))
    hardware=[]
    for part in ['sleeves','retention_washers','anchor_shanks_simplified']:
        s=shapes[part];v=volume(common_shape(s,left))+volume(common_shape(s,right));hardware.append({'part':part,'plate_overlap_mm3':v})
    sleeve_solid=shapes['sleeves'].Solids()[0];sr=sorted(set(round(q['radius_mm']*2,5) for q in cylinders(sleeve_solid)));wr=sorted(set(round(q['radius_mm']*2,5) for q in cylinders(shapes['retention_washers'].Solids()[0])))
    h_ok=all(q['plate_overlap_mm3']<=tol for q in hardware) and sr==sorted([a['sleeve_id_mm'],a['sleeve_od_mm']]) and wr==sorted([a['washer_id_mm'],a['washer_od_mm']])
    checks.append(record('hardware:actual_solids',['R04','R15'],'PASS' if h_ok else 'FAIL','Imported sleeves, washers and simplified M6 shanks have nominal diameters and no forbidden plate collision.',{'plate_intersections':hardware,'sleeve_diameters_mm':sr,'washer_diameters_mm':wr},'Nominal dimensions match config and all plate overlap volumes <=0.001mm3.','Repair actual hardware placement or component sizes; threaded/expansion details require separate catalogue/installation verification.',['cad/sleeves.step','cad/retention_washers.step','cad/anchor_shanks_simplified.step']))
    for kind in ['sleeves','retention_washers','anchor_shanks_simplified']:
        checks.append(hardware_pose_check(shapes[kind],kind,cfg))
        matches=[]
        for target in shapes[kind].Solids():
            candidates=[q for q in assembly_solids if abs(q.Volume()-target.Volume())<=tol and (q.Center()-target.Center()).Length<=dtol]
            matches.append(len(candidates)==1 and abs(volume(common_shape(candidates[0],target))-target.Volume())<=tol)
        checks.append(record('assembly:actual_hardware:'+kind,['R04','R15'],'PASS' if len(matches)==4 and all(matches) else 'FAIL','Assembly STEP contains all four hardware components in their independently checked poses.',{'matching_components':sum(matches),'expected_components':4},'Four exact component/pose matches.','Repair stale or misplaced hardware in the assembly STEP.',['cad/assembly.step','cad/'+kind+'.step']))
    vals={'minimum_sleeve_radial_clearance_mm':(c['bolt_bore_mm']-(a['sleeve_od_mm']+a['sleeve_od_tolerance_mm']))/2,'minimum_shank_diametral_clearance_mm':a['sleeve_id_mm']-a['sleeve_id_tolerance_mm']-a['thread_diameter_mm'],'minimum_sleeve_projection_mm':a['sleeve_length_mm']-a['sleeve_length_tolerance_mm']-c['plate_thickness_mm'],'minimum_washer_radial_overlap_mm':(a.get('washer_od_min_mm',a['washer_od_mm'])-c['bolt_bore_mm'])/2,'maximum_fixture_stack_mm':a['sleeve_length_mm']+a['sleeve_length_tolerance_mm']+a['washer_thickness_mm']+a['washer_thickness_tolerance_mm'],'nominal_washer_to_plate_gap_mm':a['sleeve_length_mm']-c['plate_thickness_mm']}
    ok=vals['minimum_sleeve_radial_clearance_mm']>0 and vals['minimum_shank_diametral_clearance_mm']>0 and vals['minimum_sleeve_projection_mm']+1e-8>=a['minimum_sleeve_projection_mm'] and vals['minimum_washer_radial_overlap_mm']>0 and vals['maximum_fixture_stack_mm']<=a['max_fixture_mm']
    checks.append(record('hardware:tolerance_stack',['R04','R15'],'PASS' if ok else 'FAIL','Supplier hardware tolerance stack screened against nominal printed plate; actual printed dimensions remain unmeasured.',vals,{'minimum_projection_mm':a['minimum_sleeve_projection_mm'],'maximum_fixture_mm':a['max_fixture_mm'],'positive_clearances_required':True},'Choose a compatible sleeve/washer stack and measure every printed plate before tightening anchors.',['config/design.json','cad/sleeves.step','cad/retention_washers.step']))
    min_outer=b['outer_mm']-b['outer_tolerance_mm'];max_wall=b['wall_mm']+b['wall_tolerance_mm'];min_open=min_outer-2*max_wall
    worst=rounded_tube(min_outer,min_open,b['outer_radius_mm'],b['inner_radius_mm']+b['radius_tolerance_mm'],b['length_mm'],asm['beam_start_x_mm']);wv=volume(common_shape(core,worst))
    checks.append(record('fit:catalogue_tolerance_qualification',['R03','R15'],'BLOCKED','The fixed nominal plug does not fit every allowed catalogue opening; actual purchased tube dimensions are not measured.',{'minimum_catalogue_opening_mm':min_open,'nominal_core_mm':c['plug_core_mm'],'hypothetical_minimum_opening_collision_mm3':wv,'all_catalogue_extremes_fit':wv<=tol},'Actual measured tube opening and selected fit coupon must demonstrate geometric fit; nominal STEP PASS alone cannot approve the purchased lot.','Measure both flats and corners at both tube ends, select/rebuild coupons and adapt plug core/rib dimensions to those observations; rerun this checker.',['config/design.json','config/physical_acceptance.json']))
    checks.append(record('fit:physical_press_fit',['R03','R05','R15'],'BLOCKED','CAD does not establish insertion force, rib crushing, retention, printed shrinkage or creep.',None,'Authentic print, insertion, retention and sustained-load evidence.','Print qualified material, measure openings and coupons, record insertion/retention/proof and environmental tests before release.',['config/physical_acceptance.json','manufacturing/PRINT_AND_ASSEMBLY.md']))
    counts={s:sum(q['status']==s for q in checks) for s in ['PASS','FAIL','BLOCKED','ERROR']}
    result={'schema':'cadquery-occt-fit-v1','version':'v1','created_utc':datetime.now(timezone.utc).isoformat(),'execution_complete':True,'source_provenance':'Independent audit of reconstructed v1 delivered STEP files; no original v0 geometry recovered.','versions':{'CadQuery':version('cadquery'),'cadquery-ocp_distribution':version('cadquery-ocp'),'OCP':OCP.__version__,'OpenCASCADE_kernel':'.'.join(OCP.__version__.split('.')[:3])},'kernel_operations':['BRepCheck_Analyzer','BRepCheck_Shell','BRepAlgoAPI_Common','BRepAlgoAPI_Cut','BRepExtrema_DistShapeShape'],'actual_checked_solids':{n:len(s.Solids()) for n,s in shapes.items()},'input_hashes':{p:sha(root/p) for p in inputs},'checks':checks,'summary':counts,'nominal_geometry_pass':not counts['FAIL'] and not counts['ERROR'],'physical_fit_qualified':False}
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=ROOT);a=ap.parse_args();root=a.root.resolve();(root/'results').mkdir(exist_ok=True)
    try:result=run(root)
    except Exception as exc:
        result={'schema':'cadquery-occt-fit-v1','version':'v1','execution_complete':False,'versions':{},'input_hashes':{},'checks':[record('fit:execution',['R15'],'ERROR',f'{type(exc).__name__}: {exc}',None,'All mandatory actual geometry checks must execute.','Install the pinned CadQuery/OCP dependencies and restore every required STEP/input; rerun the actual checker.',['logs/ci_<run_id>.log'])],'traceback':traceback.format_exc(),'summary':{'PASS':0,'FAIL':0,'BLOCKED':0,'ERROR':1},'nominal_geometry_pass':False,'physical_fit_qualified':False}
    (root/'results/geometric_fit.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# CadQuery and Open CASCADE geometric fit audit','',f"Execution complete: **{result['execution_complete']}**. Nominal geometry pass: **{result['nominal_geometry_pass']}**. Physical fit qualified: **False**.",'','| Check | Status | Observation and next action |','| --- | --- | --- |']
    for q in result['checks']:
        txt=q['message']+(' Next: '+q['next_action'] if q['status']!='PASS' else '')
        lines.append('| '+q['id']+' | '+q['status']+' | '+txt.replace('|','/')+' |')
    (root/'results/geometric_fit.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'geometric_fit':result['summary'],'execution_complete':result['execution_complete'],'nominal_geometry_pass':result['nominal_geometry_pass']},indent=2))
    for q in result['checks']:
        if q['status']!='PASS':print(q['status'],q['id'],q['message'],'NEXT:',q['next_action'])
    s=result['summary'];return 3 if s['ERROR'] else (1 if s['FAIL'] else (2 if s['BLOCKED'] else 0))
if __name__=='__main__':raise SystemExit(main())
