#!/usr/bin/env python3
"""Reconstruct native FreeCAD parts, STEP solids and assembly from design.json.

Run with a Python interpreter able to import FreeCAD (tested /usr/bin/python3).
The FCStd files retain named shape stages and numeric parameters; design.json and
this generator are the authoritative, fully reproducible parameterization.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
sys.path.append('/usr/lib/freecad/lib')
import FreeCAD as App
import Part

DEFAULT_ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def vec(x,y,z):return App.Vector(float(x),float(y),float(z))
def yz_face(points,x):
    pp=[vec(x,y,z) for y,z in points]
    return Part.Face(Part.makePolygon(pp+[pp[0]]))
def rounded_prism(length,width,radius,x=0):
    s=Part.makeBox(length,width,width,vec(x,-width/2,-width/2))
    es=[e for e in s.Edges if abs(e.Length-length)<1e-6]
    return s.makeFillet(radius,es)
def octagon(size,chamfer,x,length):
    h=size/2;c=chamfer
    pts=[(-h+c,-h),(h-c,-h),(h,-h+c),(h,h-c),(h-c,h),(-h+c,h),(-h,h-c),(-h,-h+c)]
    return yz_face(pts,x).extrude(vec(length,0,0))
def right_instance(shape,wall):
    s=shape.copy();s.rotate(vec(0,0,0),vec(0,0,1),180);s.translate(vec(wall,0,0));return s

def shape_data(s):
    b=s.BoundBox
    solids=s.Solids
    mass=sum(x.Volume for x in solids)
    com=[sum(x.Volume*getattr(x.CenterOfMass,a) for x in solids)/mass for a in ['x','y','z']] if mass else [0,0,0]
    return {'volume_mm3':s.Volume,'area_mm2':s.Area,'bbox_mm':{'xmin':b.XMin,'xmax':b.XMax,'ymin':b.YMin,'ymax':b.YMax,'zmin':b.ZMin,'zmax':b.ZMax},'center_mm':com,'solids':len(s.Solids),'valid':s.isValid(),'closed':bool(solids) and all(x.isClosed() for x in solids)}
def add_shape(doc,name,shape,visible=False):
    o=doc.addObject('Part::Feature',name);o.Shape=shape
    if o.ViewObject:o.ViewObject.Visibility=visible
    return o

def save_document(path,name,stages,params):
    doc=App.newDocument(name)
    p=doc.addObject('App::FeaturePython','ReconstructionParameters')
    p.addProperty('App::PropertyString','Source','Provenance').Source='Reconstructed v1 from retained v0 Google Doc and conversation; original CAD unavailable.'
    p.addProperty('App::PropertyString','DesignJSON','Parameters').DesignJSON=json.dumps(params,sort_keys=True)
    for key,val in params.items():
        if isinstance(val,(int,float)):
            pname=''.join(x.capitalize() for x in key.split('_'))
            p.addProperty('App::PropertyFloat',pname,'Parameters');setattr(p,pname,float(val))
    objs=[]
    for idx,(nm,s) in enumerate(stages):objs.append(add_shape(doc,nm,s,idx==len(stages)-1))
    doc.recompute();doc.saveAs(str(path));App.closeDocument(name)

def build(root):
    cfg=json.loads((root/'config/design.json').read_text());b=cfg['beam'];c=cfg['bracket'];a=cfg['anchors'];asm=cfg['assembly'];out=root/'cad';out.mkdir(exist_ok=True)
    plate=Part.makeBox(c['plate_thickness_mm'],c['plate_width_mm'],c['plate_height_mm'],vec(0,-c['plate_width_mm']/2,-c['plate_height_mm']/2))
    x0=c['plate_thickness_mm'];xf=x0+c['reinforcement_mm'];w=c['plate_width_mm'];zf=c['reinforcement_flat_half_height_mm'];zt=c['reinforcement_taper_half_height_mm']
    pts=[vec(x0,-w/2,-zt),vec(xf,-w/2,-zf),vec(xf,-w/2,zf),vec(x0,-w/2,zt)]
    reinforcement=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(vec(0,w,0))
    plug=octagon(c['plug_core_mm'],c['plug_corner_chamfer_mm'],xf,c['plug_projection_mm'])
    joined=plate.fuse(reinforcement).fuse(plug).removeSplitter()
    root_edges=[]
    for e in joined.Edges:
        pts=[v.Point for v in e.Vertexes]
        if len(pts)>=2 and all(abs(p.x-xf)<1e-6 for p in pts) and all(abs(p.y)<=c['plug_core_mm']/2+1e-5 and abs(p.z)<=c['plug_core_mm']/2+1e-5 for p in pts):root_edges.append(e)
    if len(root_edges)!=8:raise RuntimeError(f'Expected eight root edges, got {len(root_edges)}')
    filleted=joined.makeFillet(c['root_fillet_mm'],root_edges).removeSplitter()
    holes=[]
    for z in [-c['bolt_pitch_mm']/2,c['bolt_pitch_mm']/2]:holes.append(Part.makeCylinder(c['bolt_bore_mm']/2,x0+2,vec(-1,0,z),vec(1,0,0)))
    core=filleted
    for hole in holes: core=core.cut(hole)
    core=core.removeSplitter()
    rib_base=c['plug_core_mm']/2-c['rib_embedded_base_mm'];rib_tip=c['rib_envelope_mm']/2;rw=c['rib_width_mm']/2
    rib_template=yz_face([(rib_base,-rw),(rib_tip,0),(rib_base,rw)],c['rib_start_x_mm']).extrude(vec(c['rib_end_x_mm']-c['rib_start_x_mm'],0,0))
    ribs=[]
    for angle in [0,90,180,270]:
        s=rib_template.copy();s.rotate(vec(0,0,0),vec(1,0,0),angle);ribs.append(s)
    ribs_shape=Part.Compound(ribs)
    printable=core
    for rib in ribs: printable=printable.fuse(rib)
    printable=printable.removeSplitter()
    added_ribs=printable.cut(core).removeSplitter()
    outer=rounded_prism(b['length_mm'],b['outer_mm'],b['outer_radius_mm'],asm['beam_start_x_mm'])
    inner=rounded_prism(b['length_mm']+2,b['inner_mm'],b['inner_radius_mm'],asm['beam_start_x_mm']-1)
    beam=outer.cut(inner).removeSplitter()
    right=right_instance(printable,asm['right_wall_x_mm']);right_core=right_instance(core,asm['right_wall_x_mm'])
    sleeves=[];washers=[];bolts=[]
    for z in [-c['bolt_pitch_mm']/2,c['bolt_pitch_mm']/2]:
        sleeve=Part.makeCylinder(a['sleeve_od_mm']/2,a['sleeve_length_mm'],vec(0,0,z),vec(1,0,0)).cut(Part.makeCylinder(a['sleeve_id_mm']/2,a['sleeve_length_mm']+2,vec(-1,0,z),vec(1,0,0)))
        washer=Part.makeCylinder(a['washer_od_mm']/2,a['washer_thickness_mm'],vec(a['sleeve_length_mm'],0,z),vec(1,0,0)).cut(Part.makeCylinder(a['washer_id_mm']/2,a['washer_thickness_mm']+2,vec(a['sleeve_length_mm']-1,0,z),vec(1,0,0)))
        bolt=Part.makeCylinder(a['thread_diameter_mm']/2,a['embedment_mm']+a['sleeve_length_mm']+a['washer_thickness_mm'],vec(-a['embedment_mm'],0,z),vec(1,0,0))
        sleeves.extend([sleeve,right_instance(sleeve,asm['right_wall_x_mm'])]);washers.extend([washer,right_instance(washer,asm['right_wall_x_mm'])]);bolts.extend([bolt,right_instance(bolt,asm['right_wall_x_mm'])])
    parts={'beam_400mm':beam,'bracket':printable,'bracket_structural_core_only':core,'bracket_added_ribs':added_ribs,'bracket_right':right,'bracket_right_structural_core_only':right_core,'sleeves':Part.Compound(sleeves),'retention_washers':Part.Compound(washers),'anchor_shanks_simplified':Part.Compound(bolts)}
    for name,s in parts.items():
        if not s.isValid() or s.Volume<=0:raise RuntimeError('Invalid shape '+name)
        s.exportStep(str(out/(name+'.step')))
    assembly=Part.Compound([beam,printable,right]+sleeves+washers+bolts)
    assembly.exportStep(str(out/'assembly.step'))
    save_document(out/'bracket.FCStd','Bracket',[('WallPlate',plate),('Reinforcement',reinforcement),('ChamferedPlug',plug),('JoinedShape',joined),('RootFillet',filleted),('DrilledStructuralCore',core),('SacrificialRibs',ribs_shape),('PrintableBracket',printable)],c)
    save_document(out/'beam_400mm.FCStd','Beam400',[('RoundedOuterProfile',outer),('TubeVoid',inner),('AluminumTube400',beam)],b)
    save_document(out/'bracket_structural_core_only.FCStd','StructuralBracket',[('StructuralCore',core)],c)
    save_document(out/'assembly.FCStd','Assembly',[('Beam',beam),('LeftBracket',printable),('RightBracket',right),('Sleeves',parts['sleeves']),('RetentionWashers',parts['retention_washers']),('AnchorShanksSimplified',parts['anchor_shanks_simplified']),('FullAssembly',assembly)],asm)
    coupons=[]
    for envelope in c['fit_coupon_envelopes_mm']:
        # Same 0.30 mm difference between rib envelope and core flats; 12 mm trial insertion length.
        cb=envelope-0.30;cp=octagon(cb,c['plug_corner_chamfer_mm'],3,12)
        base=Part.makeBox(3,42,42,vec(0,-21,-21));cr=[]
        rb=cb/2-c['rib_embedded_base_mm']
        t=yz_face([(rb,-rw),(envelope/2,0),(rb,rw)],4.5).extrude(vec(9,0,0))
        for angle in [0,90,180,270]:
            q=t.copy();q.rotate(vec(0,0,0),vec(1,0,0),angle);cr.append(q)
        cs=base.fuse(cp)
        for rib in cr: cs=cs.fuse(rib)
        cs=cs.removeSplitter();name='fit_coupon_'+f'{envelope:.2f}'.replace('.','p')+'mm';cs.exportStep(str(out/(name+'.step')));coupons.append((name,cs))
    save_document(out/'fit_coupons.FCStd','FitCoupons',coupons,{'base_width_mm':42,'base_thickness_mm':3,'plug_length_mm':12})
    # Tessellation is solely for drawings; printable STL is generated separately by Gmsh.
    preview={}
    for name,s in {'beam':beam,'bracket':printable,'right_bracket':right,'core':core,**{'sleeve'+str(i):s for i,s in enumerate(sleeves)},**{'washer'+str(i):s for i,s in enumerate(washers)}}.items():
        vv,ff=s.tessellate(0.2);preview[name]={'vertices':[[v.x,v.y,v.z] for v in vv],'faces':[list(f) for f in ff]}
    (out/'preview_mesh.json').write_text(json.dumps(preview,separators=(',',':')))
    manifest={'schema':'freecad-geometry-v1','reconstructed':True,'generator':'scripts/build_cad.py','design_sha256':sha(root/'config/design.json'),'generator_sha256':sha(Path(__file__)),'FreeCAD_version':'.'.join(App.Version()[:3]),'OCC_version':Part.OCC_VERSION,'coordinates':'Global x is beam axis. Left wall x=0, beam STEP x=15.8..415.8, right wall x=431.6; right bracket is 180 degree rotation about z then translation.','geometry':{k:shape_data(s) for k,s in parts.items()},'coupons':{n:shape_data(s) for n,s in coupons},'assembly':shape_data(assembly),'root_fillet_edges':len(root_edges),'rib_reconstruction':'Four triangular sacrificial ribs; nominal 31.85 mm maximum envelope, 1.2 mm base width, 0.075 mm embedded root, x=16..44.3. These details are reconstructed and differ potentially from unrecovered v0 ribs.','anchor_geometry':'Simplified cylindrical M6 shanks only; thread, nut, supplied small washer and expansion mechanism are not modeled. Catalogue anchor capacities and physical installation are separate checks.','files':[]}
    for p in sorted(out.glob('*')):
        if p.suffix in ['.step','.FCStd']:manifest['files'].append({'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size})
    (out/'geometry_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'success':True,'root':str(root),'core_volume_mm3':core.Volume,'bracket_volume_mm3':printable.Volume,'beam_volume_mm3':beam.Volume,'root_fillet_edges':len(root_edges),'CAD_files':len(manifest['files'])},indent=2))

def validate_only(root):
    """Read current native FCStd documents without rewriting any CAD bytes."""
    manifest=json.loads((root/'cad/geometry_manifest.json').read_text())
    checks=[];paths=['config/design.json','cad/geometry_manifest.json','scripts/build_cad.py']
    targets={'bracket.FCStd':{'PrintableBracket':'bracket'},'beam_400mm.FCStd':{'AluminumTube400':'beam_400mm'},'bracket_structural_core_only.FCStd':{'StructuralCore':'bracket_structural_core_only'},'assembly.FCStd':{'FullAssembly':'assembly'},'fit_coupons.FCStd':{k:k for k in manifest['coupons']}}
    checks.append({'id':'freecad:source_manifest','requirements':['R11','R19'],'status':'PASS' if manifest['design_sha256']==sha(root/'config/design.json') and manifest['generator_sha256']==sha(Path(__file__)) else 'FAIL','message':'Native geometry is bound to current design and generator.','observed':{'design_sha256':sha(root/'config/design.json'),'generator_sha256':sha(Path(__file__))},'criterion':'Matches geometry_manifest.json','next_action':'Regenerate CAD and all dependent checks in the current version if source inputs changed.','evidence':['cad/geometry_manifest.json']})
    for fn,objects in targets.items():
        path=root/'cad'/fn;paths.append('cad/'+fn);doc=None
        try:
            doc=App.openDocument(str(path));measured={};good=True
            for objname,key in objects.items():
                obj=doc.getObject(objname)
                if obj is None or obj.Shape.isNull():raise ValueError('Missing final shape '+objname)
                actual=shape_data(obj.Shape)
                expected=manifest['assembly'] if key=='assembly' else manifest['coupons'].get(key,manifest['geometry'].get(key))
                measured[objname]=actual
                good=good and actual['valid'] and actual['closed'] and actual['solids']==expected['solids'] and abs(actual['volume_mm3']-expected['volume_mm3'])<=0.001
            checks.append({'id':'freecad:'+fn,'requirements':['R11'],'status':'PASS' if good else 'FAIL','message':'Opened native document and checked current final solids and volume without writing CAD.','observed':measured,'criterion':'Valid closed solids, expected solid count, volume agrees within0.001mm3.','next_action':'Repair invalid/stale native CAD and regenerate dependent exports.','evidence':['cad/'+fn,'cad/geometry_manifest.json']})
        except Exception as exc:
            checks.append({'id':'freecad:'+fn,'requirements':['R11'],'status':'ERROR','message':str(exc),'observed':None,'criterion':'Native document must open successfully.','next_action':'Restore native FCStd or rebuild it with the documented FreeCAD runtime.','evidence':['cad/'+fn]})
        finally:
            if doc is not None:App.closeDocument(doc.Name)
    counts={s:sum(x['status']==s for x in checks) for s in ['PASS','FAIL','BLOCKED','ERROR']}
    result={'schema':'freecad-validation-v1','execution_complete':not counts['ERROR'],'versions':{'FreeCAD':'.'.join(App.Version()[:3]),'OpenCASCADE':Part.OCC_VERSION},'input_hashes':{p:sha(root/p) for p in paths if (root/p).is_file()},'checks':checks,'summary':counts}
    (root/'results/freecad_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'FreeCAD_readonly_validation':counts},indent=2))
    return 3 if counts['ERROR'] else (1 if counts['FAIL'] else 0)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=DEFAULT_ROOT);ap.add_argument('--validate-only',action='store_true');a=ap.parse_args()
    if a.validate_only:raise SystemExit(validate_only(a.root.resolve()))
    build(a.root.resolve())
if __name__=='__main__':
    try: main()
    except Exception:
        import traceback
        msg=traceback.format_exc()
        (DEFAULT_ROOT/'logs/cad_error.txt').write_text(msg)
        print(msg,file=sys.__stderr__)
        raise SystemExit(1)
