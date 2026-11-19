#!/usr/bin/env python3
"""Reconstructed v1 analytical screens (mm, N, MPa); no physical certification."""
from __future__ import annotations
import argparse, hashlib, itertools, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rounded_square(b,r):
    if not 0<=r<=b/2:raise ValueError('Radius must lie between zero and half the width')
    c=b/2-r
    area=b*b-(4-math.pi)*r*r
    inertia=b**4/12-4*(c*c*r*r*(1-math.pi/4)+c*r**3/3+r**4*(1/3-math.pi/16))
    return area,inertia

def tube_section(b,t,ro,ri):
    if t<=0 or b<=2*t:raise ValueError('Invalid tube wall')
    ao,io=rounded_square(b,ro);ai,ii=rounded_square(b-2*t,ri)
    return ao-ai,io-ii

def chamfered_square(b,c):
    if not 0<=c<b/2:raise ValueError('Invalid chamfer')
    return b*b-2*c*c,b**4/12-4*(c*c/2*(b/2-c/3)**2+c**4/36)

def record(cid,observed,criterion,message,requirements=('R05','R08','R14'),next_action=None):
    passed=bool(observed<=criterion)
    return {'id':cid,'requirements':list(requirements),'status':'PASS' if passed else 'FAIL','observed':observed,'criterion':{'maximum':criterion},'message':message,'next_action':next_action or ('Retain this verified screen; actual physical qualification is separate.' if passed else 'Revise the load path or dimensions/material, recompute, and preserve the failed result.'),'evidence':['results/calculations.json','scripts/calculate.py']}

def calculate(cfg):
    b=cfg['beam'];p=cfg['bracket'];a=cfg['anchors'];l=cfg['loads'];ac=cfg['acceptance']
    B=b['outer_mm'];t=b['wall_mm'];ro=b['outer_radius_mm'];ri=b['inner_radius_mm'];L=b['length_mm']+b['length_tolerance_mm'];F=l['service_force_N'];g=l['gravity_m_s2'];sf=l['material_safety_factor']
    area,I=tube_section(B,t,ro,ri)
    variants=[tube_section(bv,tv,rv,iv) for bv,tv,rv,iv in itertools.product(*[(v-d,v+d) for v,d in [(B,b['outer_tolerance_mm']),(t,b['wall_tolerance_mm']),(ro,b['radius_tolerance_mm']),(ri,b['radius_tolerance_mm'])]])]
    Amin=min(x[0] for x in variants);Amax=max(x[0] for x in variants);Imin=min(x[1] for x in variants)
    bmin=B-b['outer_tolerance_mm'];bmax=B+b['outer_tolerance_mm'];tmin=t-b['wall_tolerance_mm'];cmax=bmax/2;Z=Imin/cmax
    W=Amax*L*b['density_kg_m3']*g*1e-9;q=W/L
    M=F*L/4+q*L*L/8;Me=F*cmax*math.sqrt(2)
    sigb=math.sqrt(2)*(M+Me)/Z;siga=F/Amin
    Am=rounded_square(bmin-2*(t+b['wall_tolerance_mm']),ri+b['radius_tolerance_mm'])[0];T=F*cmax*math.sqrt(2);tauT=T/(2*Am*tmin);tauV=1.5*(F+W)/(2*tmin*(bmin-2*tmin))
    vm=math.sqrt((sigb+siga)**2+3*(tauT+tauV)**2)
    E=b['E_MPa'];delta=F*L**3/(48*E*Imin)+5*q*L**4/(384*E*Imin)+Me*L*L/(8*E*Imin)
    nominal_W=area*b['length_mm']*b['density_kg_m3']*g*1e-9
    euler_nom=F*b['length_mm']**3/(48*E*I)+5*(nominal_W/b['length_mm'])*b['length_mm']**4/(384*E*I)
    Pe=math.pi**2*E*Imin/L**2;Pallow=min(Pe,b['yield_reference_MPa']*Amin)/sf
    # A deliberately loose rectangular upper bound includes reinforcement, fillet and ribs.
    vupper=p['plate_width_mm']*p['plate_height_mm']*(p['plate_thickness_mm']+p['reinforcement_mm'])+p['rib_envelope_mm']**2*(p['plug_projection_mm']+p['root_fillet_mm'])
    wp=vupper*p['density_kg_m3']*g*1e-9
    required_R=F+W+wp;required_T=(F+W)*cmax*math.sqrt(2)+wp*p['plate_width_mm']/2;required_M=M+Me
    R=l['bracket_force_envelope_N'];Tx=l['bracket_torsion_envelope_Nmm'];Mt=l['bracket_transverse_moment_envelope_Nmm'];ell=p['plug_projection_mm'];Pc=p['plug_core_mm'];C=p['plug_corner_chamfer_mm'];Ap,Ip=chamfered_square(Pc,C);Zp=Ip/(Pc/2);ins=Pc-2*C
    sp=math.sqrt(2)*(R*ell+Mt)/Zp+R/Ap;tp=1.5*R/ins**2+Tx/(.208*ins**3);plug_vm=math.sqrt(sp*sp+3*tp*tp)
    plug_delta=R*ell**3/(3*p['E_MPa']*Ip)+Mt*ell**2/(2*p['E_MPa']*Ip)
    plate_stress=(R*p['bolt_pitch_mm']/4)/(p['plate_width_mm']*p['plate_thickness_mm']**2/6)
    Fc=R+Mt/(p['engagement_mm']-10);bearing=Fc/(ins*10);wallstress=(Fc*(bmax-2*tmin)/4)/(10*tmin*tmin/6)
    e=p['plate_thickness_mm']+p['reinforcement_mm']+ell;s=p['bolt_pitch_mm'];d=a['thread_diameter_mm'];fixture=a['sleeve_length_mm']+a['sleeve_length_tolerance_mm']+a['washer_thickness_mm']+a['washer_thickness_tolerance_mm']
    N=R+(R*e+Mt)/s;V=R+Tx/s;Mb=V*(fixture+.5*d)+R*e+Mt;U=N/a['permissible_tension_N']+V/a['permissible_shear_N']+Mb/a['permissible_bending_Nmm']
    preload=[a['torque_Nm']*1000/(K*d) for K in [.25,.15]];sleeveA=math.pi/4*((a['sleeve_od_mm']-a['sleeve_od_tolerance_mm'])**2-(a['sleeve_id_mm']+a['sleeve_id_tolerance_mm'])**2)
    vals={'section_area_mm2':area,'section_I_mm4':I,'section_Amin_mm2':Amin,'section_Amax_mm2':Amax,'section_Imin_mm4':Imin,'section_Zmin_mm3':Z,'beam_weight_upper_N':W,'beam_moment_max_Nmm':M,'eccentric_axial_moment_Nmm':Me,'torsion_enclosed_area_lower_mm2':Am,'beam_torsion_shear_MPa':tauT,'beam_transverse_shear_MPa':tauV,'beam_bending_stress_MPa':sigb,'beam_global_vm_MPa':vm,'beam_local_wall_stress_MPa':wallstress,'beam_global_deflection_mm':delta,'beam_nominal_euler_deflection_mm':euler_nom,'beam_nominal_weight_N':nominal_W,'beam_euler_buckling_N':Pe,'beam_compression_allowable_N':Pallow,'beam_compression_utilization':F/Pallow,'bracket_bounding_volume_mm3':vupper,'bracket_weight_upper_N':wp,'required_bracket_force_N':required_R,'required_bracket_torsion_Nmm':required_T,'required_bracket_transverse_moment_Nmm':required_M,'plug_area_mm2':Ap,'plug_I_mm4':Ip,'plug_vm_MPa':plug_vm,'plug_deflection_mm':plug_delta,'plate_strip_stress_MPa':plate_stress,'contact_force_N':Fc,'contact_bearing_pressure_MPa':bearing,'anchor_tension_N':N,'anchor_shear_N':V,'anchor_bending_Nmm':Mb,'anchor_interaction':U,'fixture_max_mm':fixture,'preload_range_N':preload,'sleeve_min_area_mm2':sleeveA,'sleeve_compression_MPa':max(preload)/sleeveA,'aluminum_allowable_MPa':b['yield_reference_MPa']/sf,'PETG_allowable_MPa':p['strength_reference_MPa']/sf}
    checks=[]
    for cid,v,lim,msg in [('beam_global_stress',vm,vals['aluminum_allowable_MPa'],'Combined conservative beam stress screen'),('beam_local_wall_stress',wallstress,vals['aluminum_allowable_MPa'],'Local 10 mm wall-strip contact screen'),('beam_displacement',delta,ac['max_displacement_mm'],'Global all-direction beam displacement envelope'),('beam_compression',F,Pallow,'Pinned Euler and squash-load material screen'),('bracket_force_envelope',required_R,R,'Force envelope includes all beam selfweight and conservative bracket selfweight'),('bracket_torsion_envelope',required_T,Tx,'Eccentric force/selfweight torque envelope'),('bracket_transverse_moment_envelope',required_M,Mt,'Beam bending plus eccentric axial moment'),('plug_stress',plug_vm,vals['PETG_allowable_MPa'],'Chamfered plug conservative stress screen'),('plug_displacement',plug_delta,ac['max_displacement_mm'],'Isolated plug displacement screen'),('plate_strip_stress',plate_stress,vals['PETG_allowable_MPa'],'Simplified plate strip screen; FEM retains real geometry'),('bearing_pressure',bearing,vals['PETG_allowable_MPa'],'Assumed two 10 mm axial bearing patches'),('anchor_interaction',U,1,'Linear service permissible-capacity interaction'),('fixture_thickness',fixture,a['max_fixture_mm'],'Maximum sleeve plus retention washer fixture stack')]:checks.append(record('calc:'+cid,v,lim,msg))
    formulas=[['Self weight','W=Amax*L*rho*g*1e-9; q=W/L (rho in kg/m3, length in mm)'],['Bracket selfweight bound','Vp_upper=plate_width*plate_height*(base_thickness+reinforcement)+rib_envelope^2*(plug_projection+root_fillet); Wp=Vp_upper*rho_p*g*1e-9'],['Reaction envelopes','R_required=F+Wbeam+Wp; T_required=(F+Wbeam)*cmax*sqrt(2)+Wp*plate_width/2; Mt_required=Mmax+Me'],['Beam shear and torsion','Am_lower=As(bmin-2*tmax,ri_max); tau_T=(F*cmax*sqrt(2))/(2*Am_lower*tmin); tau_V=1.5*(F+W)/(2*tmin*(bmin-2*tmin))'],['Plug displacement','delta_p=R*ell^3/(3*Ep*Ip)+Mt*ell^2/(2*Ep*Ip)'],['Plate strip','sigma_plate=(R*bolt_pitch/4)/(plate_width*plate_thickness^2/6)'],['Rounded square area','As(b,r)=b^2-(4-pi)r^2'],['Rounded square inertia','Is(b,r)=b^4/12-4*((b/2-r)^2*r^2*(1-pi/4)+(b/2-r)*r^3/3+r^4*(1/3-pi/16))'],['Tube section','A=As(b,ro)-As(b-2t,ri); I=Is(b,ro)-Is(b-2t,ri)'],['Beam moment','M=F*L/4+q*L^2/8; Me=F*cmax*sqrt(2)'],['Beam stress','sigma_b=sqrt(2)*(M+Me)/Z; sigma_a=F/Amin; VM=sqrt((sigma_b+sigma_a)^2+3*(tau_T+tau_V)^2)'],['Beam deflection','delta=F*L^3/(48*E*Imin)+5*q*L^4/(384*E*Imin)+Me*L^2/(8*E*Imin)'],['Compression','Pe=pi^2*E*Imin/L^2; Pallow=min(Pe,yield*Amin)/3'],['Plug','Ap=B^2-2*C^2; Ip=B^4/12-4*((C^2/2)*(B/2-C/3)^2+C^4/36)'],['Plug stress','sigma=sqrt(2)*(R*ell+Mt)/Zp+R/Ap; tau=1.5*R/a^2+Tx/(0.208*a^3); VM=sqrt(sigma^2+3*tau^2)'],['Local contact','Fc=R+Mt/(engagement-10); p=Fc/(10*(B-2*C)); sigmawall=(Fc*(bmax-2*tmin)/4)/(10*tmin^2/6)'],['Anchor','N=R+(R*e+Mt)/s; V=R+Tx/s; Mb=V*(fixture+0.5*d)+R*e+Mt; U=N/700+V/4300+Mb/6285.714'],['Sleeve preload','Fpre=Tinst/(K*d), K=0.15..0.25; compression=Fpre/Asleeve']]
    return {'schema':'analytical-screens-v1','version':'v1','execution_complete':True,'values':vals,'formulas':formulas,'checks':checks,'assumptions':['All quantities mm, N, MPa unless named otherwise.','Independent dimensional tolerance extremes form a conservative envelope.','PETG 14 MPa is a typical-data screening reference, not a qualified print allowable.','Closed-section torsion remains a thin-wall screening approximation; enclosed area uses the smallest tolerance-envelope inner void, conservatively below the median enclosed area.','Ribs carry no credited structural load. Contact patches, wall identity and torque load path require physical qualification.','Bracket selfweight uses an explicit bounding rectangular volume, not the historical v0 mass.','Preload/sleeve compression is an estimate; no qualified sleeve-bearing or washer-preload PASS is asserted.']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);a=ap.parse_args();r=a.root.resolve();cfg=json.loads((r/'config/design.json').read_text());out=calculate(cfg);out['input_hashes']={'config/design.json':sha(r/'config/design.json'),'scripts/calculate.py':sha(__file__)}
    (r/'results').mkdir(exist_ok=True);(r/'results/calculations.json').write_text(json.dumps(out,indent=2)+'\n')
    lines=['# v1 analytical calculations','','Fresh calculations for reconstructed v1. Historical v0 FEM values are not used.','','## Formulas','']+[f'- **{n}:** `{f}`' for n,f in out['formulas']]+['','## Calculated values','','| Quantity | Value |','| --- | --- |']+[f'| {k} | {v:.9g} |' if isinstance(v,(float,int)) else f'| {k} | {v} |' for k,v in out['values'].items()]+['','## Checks','','| Check | Status | Observed | Limit |','| --- | --- | --- | --- |']+[f"| {c['id']} | {c['status']} | {c['observed']:.9g} | {c['criterion']['maximum']:.9g} |" for c in out['checks']]+['','## Model limits','']+out['assumptions'];(r/'results/calculations.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'stage':'calculations','checks':len(out['checks']),'PASS':sum(x['status']=='PASS' for x in out['checks']),'FAIL':sum(x['status']=='FAIL' for x in out['checks'])}));return 0 if all(c['status']=='PASS' for c in out['checks']) else 1
if __name__=='__main__':raise SystemExit(main())
