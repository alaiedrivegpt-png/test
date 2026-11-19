#!/usr/bin/env python3
"""Build the v1 engineering report from current project evidence and executed results.

The 22 native editable Office Math expressions are retained from the archived v0
report export; all numeric substitutions, geometry, fit and FEM values are read
from current v1 JSON results. A missing result is never replaced by a v0 result.
Run with the documented Python dependencies, then title-sanitize and render/QA.
"""
from __future__ import annotations
import argparse,copy,csv,hashlib,json,re
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
EQ_LATEX=[
r'A_s(b,r)=b^2-(4-\pi)r^2,\quad c=b/2-r',
r'I_s(b,r)=\frac{b^4}{12}-4[c^2r^2(1-\pi/4)+cr^3/3+r^4(1/3-\pi/16)]',
r'A=A_s(b,r_o)-A_s(b-2t,r_i),\quad I=I_s(b,r_o)-I_s(b-2t,r_i)',
r'W=A_{max}L\rho g\,10^{-9},\quad q=W/L',
r'M_{max}=FL/4+qL^2/8',
r'M_e=Fc_{max}\sqrt2,\quad\sigma_b=\sqrt2(M_{max}+M_e)/Z,\quad\sigma_a=F/A_{min}',
r'T=Fc_{max}\sqrt2,\quad\tau_T=T/(2A_m t_{min}),\quad\tau_V=1.5(F+W)/[2t_{min}(b_{min}-2t_{min})]',
r'\sigma_{vm}=\sqrt{(\sigma_b+\sigma_a)^2+3(\tau_T+\tau_V)^2}',
r'\delta=FL^3/(48EI)+5qL^4/(384EI)+M_eL^2/(8EI)',
r'P_E=\pi^2EI/L^2,\quad P_{allow}=\min(P_E,\sigma_yA_{min})/3',
r'A_p=B^2-2C^2',
r'I_p=B^4/12-4[(C^2/2)(B/2-C/3)^2+C^4/36],\quad Z_p=I_p/(B/2)',
r'\sigma_p=\sqrt2(R\ell+M_t)/Z_p+R/A_p,\quad\tau_p=1.5R/a^2+T/(0.208a^3)',
r'\sigma_{p,vm}=\sqrt{\sigma_p^2+3\tau_p^2},\quad\delta_p=R\ell^3/(3E_pI_p)+M_t\ell^2/(2E_pI_p)',
r'\sigma_{plate}=(Rs/4)/(wt_p^2/6),\quad F_c=R+M_t/(\ell_{eng}-10)',
r'p_{bearing}=F_c/[(B-2C)10],\quad\sigma_{wall}=[F_c(b_{max}-2t_{min})/4]/(10t_{min}^2/6)',
r't_{fix,max}=(8+0.1)+(1.5+0.3)=9.9\;\mathrm{mm}\le10\;\mathrm{mm}',
r'N=R+(Re+M_t)/s,\quad V=R+T/s',
r'M_b=V(t_{fix,max}+0.5d)+Re+M_t',
r'U=N/700+V/4300+M_b/6285.714\le1',
r'F_{pre}=T_{inst}/(Kd),\quad A_{s,min}=\pi(17.6^2-6.5^2)/4',
r'S_{bound}=\sqrt{S_{fx}^2+S_{fy}^2+S_{fz}^2}+S_{tx}+\sqrt{S_{my}^2+S_{mz}^2}'
]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,allow=False):
    if Path(p).is_file():return json.loads(Path(p).read_text())
    if allow:return {}
    raise FileNotFoundError(p)
def f(v,d=3):
    if v is None:return 'Pending executed v1 result'
    if isinstance(v,(float,int)):return f'{v:,.{d}f}'
    return str(v)
def prose(s):
    s=str(s).replace('mm2','mm²').replace('mm3','mm³').replace('mm4','mm⁴').replace('m/s2','m/s²').replace('kg/m3','kg/m³')
    # Preserve exact catalogue codes such as EN1A, IDF17558 and M6.
    s=re.sub(r'\b(?=[A-Za-z]{2})([A-Za-z]*[a-z][A-Za-z]*)(?=[0-9])',r'\1 ',s)
    s=re.sub(r'(?<=[0-9])(?=(?:mm|MPa|GPa|kg|g|N|inch)\b)',' ',s)
    s=re.sub(r'(?<=[,;])(?=[A-Za-z])',' ',s)
    s=re.sub(r';(?=\S)','; ',s)
    s=re.sub(r'(?<=[A-Za-z%]),(?=[0-9])',', ',s)
    s=re.sub(r'(?<=\s)x(?=[0-9])','x ',s)
    s=s.replace('A6 mm','A 6 mm').replace('A2 mm','A 2 mm').replace('B2216061','B221 6061').replace('coreB=','core B=').replace('chamferC=','chamfer C=').replace('sidea=','side a=').replace('factorK=','factor K=')
    return s
def short(v,limit=170):
    s=json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)
    return s if len(s)<=limit else s[:limit-3]+'...'
class Writer:
    def __init__(self,root,maths):
        self.root=root;self.d=Document();self.md=[];self.maths=maths;self.images=[];self.newpage=False
        self.d.core_properties.title='400 mm beam wall mount engineering report v1'
        self.d.core_properties.subject='Reconstructed design, fit verification and executed finite element analysis'
        self.d.core_properties.author='Beam wall mount project'
        self.d.core_properties.keywords='v1, reconstruction, FreeCAD, CadQuery, Open CASCADE, Gmsh, CalculiX'
        sec=self.d.sections[0];sec.page_width=Inches(8.5);sec.page_height=Inches(11);sec.top_margin=Inches(.65);sec.bottom_margin=Inches(.65);sec.left_margin=Inches(.7);sec.right_margin=Inches(.7)
        styles=self.d.styles
        normal=styles['Normal'];normal.font.name='Calibri';normal.font.size=Pt(11);normal.font.color.rgb=RGBColor(0,0,0);normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.06
        for nm,sz in [('Title',22),('Subtitle',12),('Heading 1',17),('Heading 2',13)]:
            st=styles[nm];st.font.name='Calibri';st.font.size=Pt(sz);st.font.color.rgb=RGBColor(0,0,0);st.paragraph_format.space_after=Pt(8);st.paragraph_format.space_before=Pt(10 if nm.startswith('Heading') else 0)
        styles['Title'].font.bold=True
        footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
        run=footer.add_run('Beam wall mount v1  |  ');run.font.size=Pt(8);run.font.color.rgb=RGBColor(80,80,80)
        fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
    def title(self,s):self.d.add_paragraph(s,'Title');self.md+=['# '+s,'']
    def h(self,s,level=1):
        p=self.d.add_heading(s,level)
        if self.newpage:p.paragraph_format.page_break_before=True;self.newpage=False
        self.md+=['#'*(level+1)+' '+s,'']
    def p(self,s,bold=False,size=None):
        s=prose(s);p=self.d.add_paragraph();r=p.add_run(s);r.bold=bold
        if size:r.font.size=Pt(size)
        self.md+=[('**'+s+'**') if bold else s,''];return p
    def code(self,s):
        p=self.d.add_paragraph();p.paragraph_format.line_spacing=1.0
        run=p.add_run(s);run.font.name='Liberation Mono';run.font.size=Pt(9.5)
        self.md+=['```sh',s,'```',''];return p
    def page(self):self.newpage=True
    def eq(self,n):
        p=self.d.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(7);p.paragraph_format.keep_together=True
        eq=copy.deepcopy(self.maths[n-1])
        if n in {18,19}:
            # LibreOffice treats the joined letters Re as its real-part
            # operator. These anchor formulas mean force times eccentricity.
            for text_node in eq.findall('.//'+qn('m:t')):
                if text_node.text:text_node.text=text_node.text.replace('Re','R · e')
        # Google Docs export omitted the degree element from hidden-degree
        # radicals. Add the empty mandatory slot so LibreOffice preserves the
        # radicand and following terms while keeping the formula editable.
        for radical in eq.findall('.//'+qn('m:rad')):
            if radical.find(qn('m:deg')) is None:
                body=radical.find(qn('m:e'))
                radical.insert(list(radical).index(body),OxmlElement('m:deg'))
        for pr in eq.findall('.//'+qn('w:rPr')):
            sz=pr.find(qn('w:sz'))
            if sz is None:sz=OxmlElement('w:sz');pr.append(sz)
            sz.set(qn('w:val'),'22')
        p._p.append(eq);self.md+=['$$',EQ_LATEX[n-1],'$$','']
    def table(self,heads,rows,widths=None,size=9.5):
        rows=[[prose(value) for value in row] for row in rows]
        t=self.d.add_table(rows=1,cols=len(heads));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
        if widths:
            for c,w in zip(t.columns,widths):c.width=Inches(w)
        pr=t._tbl.tblPr;borders=OxmlElement('w:tblBorders')
        for edge in ['top','left','bottom','right','insideH','insideV']:
            e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
        pr.append(borders)
        for i,h in enumerate(heads):t.rows[0].cells[i].text=h
        rep=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(rep)
        for row in rows:
            cells=t.add_row().cells
            for i,v in enumerate(row):cells[i].text=prose(v)
        for ri,row in enumerate(t.rows):
            for ci,c in enumerate(row.cells):
                if widths:c.width=Inches(widths[ci])
                c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                props=c._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
                for edge in ['top','left','bottom','right']:
                    e=OxmlElement('w:'+edge);e.set(qn('w:w'),'70');e.set(qn('w:type'),'dxa');mar.append(e)
                props.append(mar);shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'243C50' if ri==0 else ('F2F5F7' if ri%2==0 else 'FFFFFF'));props.append(shade)
                for p in c.paragraphs:
                    p.paragraph_format.space_after=Pt(2);p.paragraph_format.space_before=Pt(2);p.paragraph_format.line_spacing=1.0
                    for r in p.runs:r.font.size=Pt(size);r.bold=ri==0;r.font.color.rgb=RGBColor(255,255,255) if ri==0 else RGBColor(0,0,0)
                if ri==0:
                    for p in c.paragraphs:p.paragraph_format.keep_with_next=True
        self.d.add_paragraph().paragraph_format.space_after=Pt(1)
        self.md+=['| '+' | '.join(heads)+' |','| '+' | '.join(['---']*len(heads))+' |']+['| '+' | '.join(str(x).replace('|','/') for x in r)+' |' for r in rows]+[''];return t
    def picture(self,path,caption,width=6.1,max_height=3.2):
        p=self.root/path
        if p.exists():
            with Image.open(p) as im:width=min(width,max_height*im.width/im.height)
            par=self.d.add_paragraph();par.alignment=WD_ALIGN_PARAGRAPH.CENTER;par.paragraph_format.keep_with_next=True;par.add_run().add_picture(str(p),width=Inches(width));self.images.append(path)
            self.p(caption,size=9);self.md+=['!['+caption+'](../'+path+')','']
        else:self.p('Draft figure pending: '+caption)
    def link(self,text,url):
        text=prose(text)
        p=self.d.add_paragraph();h=OxmlElement('w:hyperlink');h.set(qn('r:id'),p.part.relate_to(url,RT.HYPERLINK,is_external=True));r=OxmlElement('w:r');pr=OxmlElement('w:rPr');color=OxmlElement('w:color');color.set(qn('w:val'),'164B70');pr.append(color);sz=OxmlElement('w:sz');sz.set(qn('w:val'),'18');pr.append(sz);r.append(pr);tx=OxmlElement('w:t');tx.text=text;r.append(tx);h.append(r);p._p.append(h);p.paragraph_format.space_after=Pt(4);self.md+=['['+text+']('+url+')','']
    def save(self):
        # Built-in Word Title styles can contain a blue paragraph rule that
        # persists on Google Docs import. Strip that residue deterministically.
        for style in self.d.styles:
            if style.style_id.lower()=='title' or style.name.lower()=='title':
                for node in list(style.element.iter()):
                    if node.tag in {qn('w:pBdr'),qn('w:u')} and node.getparent() is not None:node.getparent().remove(node)
        for i,p in enumerate(self.d.paragraphs):
            if p.style.name=='Title' or i<6:
                for node in list(p._p.iter()):
                    if node.tag==qn('w:pBdr') or (p.style.name=='Title' and node.tag==qn('w:u')):
                        if node.getparent() is not None:node.getparent().remove(node)
        self.d.save(self.root/'report/report.docx');(self.root/'report/report.md').write_text('\n'.join(self.md)+'\n')
def severity(checks):
    states=[x.get('status') for x in checks]
    return 'ERROR' if 'ERROR' in states else 'FAIL' if 'FAIL' in states else 'BLOCKED' if 'BLOCKED' in states else 'PASS' if states else 'PENDING'
def checks_from(*data):return [x for d in data for x in d.get('checks',[])]
def find_check(data,word):return next((x for x in data.get('checks',[]) if word in x.get('id','')),None)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--allow-incomplete',action='store_true');a=ap.parse_args();r=a.root.resolve();draft=a.allow_incomplete
    cfg=load(r/'config/design.json');geo=load(r/'cad/geometry_manifest.json',draft);calc=load(r/'results/calculations.json',draft);fit=load(r/'results/geometric_fit.json',draft);fem=load(r/'results/fem_summary.json',draft);bom=load(r/'results/bom_summary.json',draft);sources=load(r/'evidence/source_manifest.json');ci=load(r/'results/ci_summary.json',True);selftest=load(r/'results/selftest_summary.json',draft)
    vals=calc.get('values',{});br=cfg['bracket'];be=cfg['beam'];an=cfg['anchors'];lo=cfg['loads']
    if not draft:
        if fem.get('execution_complete') is not True or fem.get('partial_development_run') is True:
            raise ValueError('Report requires a complete executed v1 FEM sweep, not a development subset')
        if selftest.get('test_system_functional') is not True or selftest.get('exit_code')!=0:
            raise ValueError('Report requires an executed passing CI self-test with a saved log')
        for path in ['drawings/assembly.png','drawings/bracket_detail.png','results/bracket_stress.png','results/beam_stress.png']:
            if not (r/path).is_file():raise FileNotFoundError('Final report figure missing: '+path)
        for data in [calc,fit,fem,bom]:
            for path,digest in data.get('input_hashes',{}).items():
                q=r/path
                if not q.exists() or sha(q)!=digest:raise ValueError('Stale report source: '+path)
        if geo.get('design_sha256')!=sha(r/'config/design.json'):raise ValueError('Geometry and design hashes disagree')
    with ZipFile(r/'evidence/v0_report_export.docx') as z:maths=etree.fromstring(z.read('word/document.xml')).findall('.//{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath')
    if len(maths)!=22:raise ValueError('Expected 22 native source equations')
    w=Writer(r,maths);all_num=checks_from(calc,fem);num_state=severity(all_num);fit_state=severity(fit.get('checks',[]));failures=[x for x in all_num if x.get('status') in {'FAIL','ERROR'}]
    w.title('400 mm beam wall mount engineering report v1')
    w.p('Reconstructed design and verification record    19 November 2026',size=11)
    w.p('This version reconstructs the 400 mm aluminum beam and its two printed end brackets from the retained v0 report and conversation. It adds independent CadQuery and Open CASCADE fit checks, executable CI checks, saved run logs and instructions for the next iteration. The original v0 CAD and solver bytes were unavailable; all v1 geometry and numerical results are newly generated.')
    nominal_fit_state='PASS' if fit.get('nominal_geometry_pass') else 'FAIL' if fit.get('execution_complete') else 'PENDING'
    w.p(f'Numerical verification: {num_state}. Nominal CAD fit: {nominal_fit_state}. Manufactured fit and physical qualification: BLOCKED. Engineering release is not approved.',bold=True)
    if failures:
        descriptions=[]
        for check in failures[:4]:
            cid=check['id'];ob=check.get('observed');criterion=check.get('criterion')
            if ':convergence:' in cid and isinstance(ob,dict):
                label=cid.split(':')[2]+' '+('displacement' if 'displacement' in cid else 'principal stress' if 'principal' in cid else 'stress')
                descriptions.append(label+' mesh change '+f(ob['relative_change']*100,1)+'% exceeds '+f(criterion*100,0)+'%')
            elif cid=='fem:Euler_comparison' and isinstance(ob,dict):descriptions.append('beam section deflection differs from Euler theory by '+f(ob['relative_difference']*100,1)+'%')
            else:descriptions.append(check.get('message',cid)+' ('+short(ob,60)+')')
        w.p('Numerical issues to resolve: '+ '; '.join(descriptions)+'. The detailed tables and machine-readable checks retain all failures.',size=10)
    w.picture('drawings/assembly.png','Figure 1  Reconstructed FreeCAD assembly. The beam is 400 mm long; nominal wall bearing faces are 431.6 mm apart.',6.2,2.5)
    w.table(['Design quantity','v1 selection'],[['Beam','Online Metals23437;6061-T6 square tube'],['Finished beam length','400 +/-0.5 mm'],['Wall bearing-face spacing','431.6 mm'],['Printed brackets','Two reinforced Prusament PETG parts'],['Load screen','10 N quasistatic force in any direction plus selfweight'],['Material screen factor','3 for aluminum and PETG only']], [2.5,4.4],10)
    w.p('The force may act at any span station with a contact footprint of at least10 x10 mm. Anchor capacities use a separate service-load interaction. Load duration, environment, actual fit and installation remain unqualified.',size=10)
    w.page();w.h('Reconstructed geometry and assembly')
    w.p('The flange is7.8 mm thick at the bolt mounts. A6 mm central reinforcement has a flat face over z=+/-20 mm and tapers to the flange at z=+/-45 mm. The plug begins at x=13.8 mm and projects32 mm. A2 mm root-relief gap leaves30 mm of tube engagement. The8-edge root fillet has2 mm radius.')
    w.picture('drawings/bracket_detail.png','Figure 2  The printable v1 bracket. Four triangular fit ribs are reconstructed explicitly and are not credited with structural strength.',5.3,3.3)
    w.table(['Feature','Dimension','Purpose'],[['Flange','60 x150 mm','Two anchor mounts'],['Anchor pitch and bores','120 mm;diameter18.6 mm','Steel sleeves and M6 passage'],['Core and rib envelope','31.55 /31.85 mm','Nominal clearance and sacrificial interference'],['Plug corner chamfer','3 mm','Clear the rounded tube opening'],['Ribs','1.2 mm base width;x16 to44.3 mm','Newly specified triangular ribs'],['Insertion allowance','2 mm root relief;30 mm engagement','Avoid tube contact with the root fillet']], [1.8,2.1,3],9.5)
    w.p('The v1 rib and coupon details are reconstructed, so their volume can differ from v0. Both bracket instances and the actual delivered STEP solids are checked. Simplified anchor shanks show placement; thread, nut, expansion clip and supplied small washer are not modeled.',size=10)
    w.page();w.h('Materials evidence and rounded tube section')
    w.p('Online Metals23437 identifies ASTM B2216061-T6 extrusion,1.5 inch outside width,0.125 inch wall,0.125 inch outer radius and0.062 inch inner radius. The actual nominal section therefore includes rounded corners [S1].')
    w.table(['Input','Value used','Basis'],[['Aluminum E /nu','68,947.57 MPa /0.33','Typical alloy guide [S5]'],['Aluminum yield reference','240 MPa','Generic extrusion minimum [S4]'],['Aluminum density','2800 kg/m3','Conservative rounded guide assumption [S5]'],['PETG E /strength reference','1400 /14 MPa','Lower typical references from specimen data [S6]'],['PETG density /nu','1270 kg/m3 /0.38','Density published;nu assumed [S6]']], [2.15,1.9,2.85],9.5)
    w.p('The PETG sheet gives interlayer adhesion18 +/-4 MPa and horizontal tensile modulus1.5 +/-0.1 GPa. These are typical test results, not a qualified allowable for the actual print. The aluminum reference is not a certificate for the purchased stock. Retain lot and process qualification gates [S4 S6].',size=10)
    for n in [1,2,3]:w.eq(n)
    w.p(f"At nominal dimensions, A={f(vals.get('section_area_mm2'))} mm2 and I={f(vals.get('section_I_mm4'))} mm4. The tolerance enumeration uses outside flats +/-0.635 mm, wall +/-0.2032 mm and corner radii +/-0.396875 mm [S2]. It gives Amin={f(vals.get('section_Amin_mm2'))} mm2, Amax={f(vals.get('section_Amax_mm2'))} mm2, Imin={f(vals.get('section_Imin_mm4'))} mm4 and Zmin={f(vals.get('section_Zmin_mm3'))} mm3.")
    w.p('Independent numerical integration checks the section formula. Tolerance extremes are combined conservatively; the actual tube opening still must be measured. A fixed nominal plug is not guaranteed to fit the full catalogue tolerance range.',size=10)
    w.page();w.h('Beam force stress and displacement calculations')
    w.p('Use the upper finished span L=400.5 mm,F=10 N and g=9.80665 m/s2. The beam bending model applies selfweight as a uniform load. The bracket envelope separately assigns all beam weight to one bracket.')
    w.p('Here b is the outside width, t the wall, cmax=bmax/2 and Z=Imin/cmax. The thin-wall torsion approximation uses a deliberately small enclosed area: Am=As(bmin−2tmax,ri,max), the rounded minimum inner opening. All section dimensions are in mm; E and stresses are in MPa.',size=10)
    for n in [4,5,6,7,8]:w.eq(n)
    w.p(f"W={f(vals.get('beam_weight_upper_N'))} N;Mmax={f(vals.get('beam_moment_max_Nmm'))} N mm;Me={f(vals.get('eccentric_axial_moment_Nmm'))} N mm. The diagonal factor bounds transverse force direction. Combined beam stress is{f(vals.get('beam_global_vm_MPa'),6)} MPa against240/3=80 MPa.")
    w.eq(9);w.p(f"The calculated global beam displacement envelope is{f(vals.get('beam_global_deflection_mm'),8)} mm against1 mm. With nominal dimensions, centered vertical force and no end eccentricity, the comparable Euler section displacement is{f(vals.get('beam_nominal_euler_deflection_mm'),8)} mm. The FEM comparison uses a sidewall section mean; local indentation is reported separately.")
    w.eq(10);w.p(f"The pinned Euler compression screen gives PE={f(vals.get('beam_euler_buckling_N'),1)} N and Pallow={f(vals.get('beam_compression_allowable_N'),1)} N. The10 N axial utilization is{f(vals.get('beam_compression_utilization'),7)}.",size=10)
    w.page();w.h('Bracket and contact analytical screens')
    w.p(f"The bounding bracket volume is{f(vals.get('bracket_bounding_volume_mm3'),1)} mm3, deliberately above the actual CAD volume. Required force{f(vals.get('required_bracket_force_N'))} N, torsion{f(vals.get('required_bracket_torsion_Nmm'))} N mm and transverse moment{f(vals.get('required_bracket_transverse_moment_Nmm'))} N mm remain within the independently applied20 N,550 N mm and1600 N mm envelopes.")
    w.p('For the screens below, R=20 N, T=550 N mm, Mt=1600 N mm, plug length ℓ=32 mm, anchor pitch s=120 mm, plate strip width w=60 mm and plate thickness tp=7.8 mm.',size=10)
    for n in [11,12,13,14]:w.eq(n)
    w.p(f"With coreB=31.55 mm and chamferC=3 mm, Ap={f(vals.get('plug_area_mm2'))} mm2 and Ip={f(vals.get('plug_I_mm4'))} mm4. The inscribed square for shear/torsion has sidea=B-2C=25.55 mm. Plug stress is{f(vals.get('plug_vm_MPa'))} MPa against14/3=4.667 MPa; isolated plug displacement is{f(vals.get('plug_deflection_mm'),5)} mm.")
    for n in [15,16]:w.eq(n)
    w.p(f"The plate strip stress is{f(vals.get('plate_strip_stress_MPa'))} MPa. Two assumed10 mm bearing patches in30 mm engagement have centers20 mm apart:Fc=20+1600/20=100 N. Bearing pressure is{f(vals.get('contact_bearing_pressure_MPa'))} MPa. The local tube wall strip gives{f(vals.get('beam_local_wall_stress_MPa'))} MPa against80 MPa.",size=10)
    w.p('The contact patches are screening assumptions. Smaller edge contacts, rib crushing, assembly misalignment, anisotropy and long-term bearing require qualification. The finite element model excludes fit ribs from credited structural material.',size=10)
    w.page();w.h('Anchors sleeves and installation load path')
    w.p('Each bracket uses two fischer564572 M6 anchors at120 mm pitch. The provisional wall is dry, sound solid C20/25 concrete, at least100 mm thick and60 mm from every free edge. The manufacturer requires6 mm drilling,60 mm minimum through-fixing hole depth and8 N m torque [S8 S9 S14].')
    w.p('An8 mm EN1A sleeve bypasses tightening compression around the printed plate. The30 mm retention washer spans the18.6 mm bore; retain the supplied anchor washer and nut above it. Each measured sleeve must project at least0.1 mm above the print. Nominal projection is0.2 mm, so the washer does not initially clamp the print [S10 S11].')
    w.eq(17)
    for n in [18,19,20]:w.eq(n)
    w.p(f"Using e=45.8 mm,s=120 mm,d=6 mm gives N={f(vals.get('anchor_tension_N'))} N,V={f(vals.get('anchor_shear_N'))} N and Mb={f(vals.get('anchor_bending_Nmm'))} N mm. The linear interaction is{f(vals.get('anchor_interaction'),6)}. One bolt is conservatively assigned the full direct load and global moment because equal sharing is not guaranteed.")
    w.p('The service references700 N tension and4300 N shear come from the published isolated-anchor table in cracked C20/25. The bending reference is11 N m/(1.25 x1.4)=6285.714 N mm. This screen does not replace the complete fastening design or qualify the custom fixture [S9 S14].',size=10)
    w.eq(21);w.p(f"With assumed torque factorK=0.15 to0.25, estimated preload is5333 to8889 N. Minimum sleeve area is{f(vals.get('sleeve_min_area_mm2'))} mm2 and nominal compression screen is{f(vals.get('sleeve_compression_MPa'))} MPa. Actual washer bending, concrete bearing and preload remain unqualified.",size=10)
    w.page();w.h('Independent geometric fit verification')
    w.p('CadQuery2.7.0 imports the delivered STEP solids and uses Open CASCADE 7.8.1 to check validity, solid volumes, dimensions, poses and Boolean intersections. The tests use both physical end instances. They distinguish unwanted core collision from intentional sacrificial-rib interference and sample the insertion path before final seating.')
    byid={c['id']:c for c in fit.get('checks',[])}
    def observed(cid,key):return byid.get(cid,{}).get('observed',{}).get(key)
    fitrows=[]
    for side in ['left','right']:
        for label,suffix,key,unit in [('Core collision','core_collision','intersection_volume_mm3','mm³'),('Minimum core clearance','core_clearance','clearance_mm','mm'),('Intended rib intersection','intentional_interference','total_interference_mm3','mm³'),('Sampled insertion core collision','sampled_insertion_path','maximum_intersection_mm3','mm³')]:
            cid='fit:'+side+':'+suffix;fitrows.append([side.title()+' '+label.lower(),byid.get(cid,{}).get('status','PENDING'),f(observed(cid,key),6)+' '+unit])
    for label,cid,key,unit in [('Engagement at each end','fit:engagement_and_relief','left_engagement_mm','mm'),('Minimum sleeve clearance','hardware:tolerance_stack','minimum_sleeve_radial_clearance_mm','mm radial'),('Minimum washer overlap','hardware:tolerance_stack','minimum_washer_radial_overlap_mm','mm radial'),('Maximum fixture stack','hardware:tolerance_stack','maximum_fixture_stack_mm','mm')]:
        fitrows.append([label,byid.get(cid,{}).get('status','PENDING'),f(observed(cid,key),3)+' '+unit])
    fitrows += [['Catalogue tolerance qualification','BLOCKED','Minimum catalogue opening30.7086 mm; nominal core31.55 mm'],['Physical press fit','BLOCKED','No measured print/stock insertion or retention evidence']]
    w.table(['Geometric check','Status','Observed result'],fitrows,[2.7,.8,3.4],9)
    w.p(f"The kernel also checks all delivered solids, exact rounded profile, opposite-end pose, assembly instances, hardware bores and the complete dimensional stack. Current nominal geometry status: {nominal_fit_state}. The full machine-readable observations are in results/geometric_fit.json.",size=10)
    w.p('All nominal checks are geometric statements about the reconstructed model. The catalogue tube opening can vary enough to defeat the fixed nominal plug. Measure both ends, select or regenerate fit coupons, and document insertion and retention before accepting a manufactured assembly. CAD cannot establish insertion force, rib crushing, print shrinkage or creep.',size=10)
    w.p('The test suite deliberately introduces defects such as an oversized or shifted core. Successful detection is evidence that the checks execute and discriminate failures. It does not change a failing engineering requirement to PASS.',size=10)
    w.page();w.h('Finite element model and bracket stress')
    w.p('Gmsh4.15.2 builds quadratic tetrahedral meshes for the reconstructed parts [M2]. CalculiX2.23 solves six linear bracket cases: three20 N force directions,550 N mm torsion and two1600 N mm transverse moments. The core includes the root fillet and reinforcement. The isotropic PETG model uses E=1400 MPa and nu=0.38.')
    w.p('The idealized attachment restrains transverse motion at sleeve bores and axial motion at wall/washer annuli. It assumes engaged bilateral contact. The actual0.2 mm washer gap, slip, preload, friction and contact opening are not solved. These limitations require later contact analysis and physical qualification.',size=10)
    w.eq(22)
    w.p('For each stress measure, the bound combines the norm of three force-case responses, the torsional response and the norm of two moment-case responses. Principal stress uses the spectral norm of the stress tensor. Nodal and integration-point maxima are retained without excluding peaks. A low stress magnitude does not establish mesh convergence.',size=10)
    w.picture('results/bracket_stress.png','Figure 3  Actual v1 CalculiX bracket stress fields and the conservative directional envelope. The figure records the current mesh and verification status.',6.2,3.3)
    bracket_levels=sorted([x for x in fem.get('levels',[]) if x.get('part')=='bracket'],key=lambda x:x['size_mm'],reverse=True)
    if bracket_levels:
        w.table(['Mesh h (mm)','Elements','VM bound (MPa)','Principal bound (MPa)','Displacement (mm)'],[[f(x['size_mm'],1),f(x['elements'],0),f(x.get('max_vm_bound_MPa'),4),f(x.get('max_principal_abs_bound_MPa'),4),f(x.get('max_displacement_bound_mm'),6)] for x in bracket_levels],[1.05,1.0,1.5,1.65,1.7],8.7)
    w.page();w.h('Beam finite element results and mesh verification')
    w.p('The beam model applies the centered10 N load patch and gravity to nominal rounded geometry, with simply supported end sections and one axial restraint. A swept tetrahedral mesh starts from the actual STEP end face. Straight-sided quadratic displacement elements use an exact100 mm2 pressure patch integrated with clipped quadratic face shape functions. Gravity uses actual finite element volume; a separate gate compares that volume with CAD.',size=10)
    w.picture('results/beam_stress.png','Figure 4  Actual v1 beam nodal stress field. Local displacement and the global section bending comparison are reported separately.',6.2,2.05)
    beam_levels=sorted([x for x in fem.get('levels',[]) if x.get('part')=='beam'],key=lambda x:x['size_mm'],reverse=True)
    if beam_levels:
        w.table(['Mesh h (mm)','Elements','Nodal VM (MPa)','IP VM (MPa)','Local displacement (mm)'],[[f(x['size_mm'],1),f(x['elements'],0),f(x.get('max_nodal_vm_MPa'),4),f(x.get('max_IP_vm_MPa'),4),f(x.get('max_displacement_mm'),6)] for x in beam_levels],[1.05,1.0,1.5,1.65,1.7],8.7)
    femrows=[]
    labels={'max_vm_bound_MPa':'bracket VM bound','max_principal_abs_bound_MPa':'bracket principal bound','max_displacement_bound_mm':'bracket displacement','max_nodal_vm_MPa':'beam nodal VM','max_IP_vm_MPa':'beam IP VM','max_displacement_mm':'beam displacement'}
    for c in fem.get('checks',[]):
        cid=c.get('id','');ob=c.get('observed');criterion=c.get('criterion')
        if cid.startswith('fem:convergence:'):
            femrows.append(['Change in '+labels.get(cid.split(':')[-1],cid),c['status'],f(ob['relative_change']*100,2)+'%',f(criterion*100,0)+'%'])
        elif cid=='fem:Euler_comparison':femrows.append(['FEM / Euler section difference',c['status'],f(ob['relative_difference']*100,2)+'%',f(criterion*100,0)+'%'])
    if femrows:w.table(['Verification','Status','Observed','Limit'],femrows,[3.5,.8,1.3,1.3],8.7)
    if beam_levels:
        fine=beam_levels[-1];allcases=[c for x in fem.get('levels',[]) for c in x.get('cases',[])]
        w.p(f"Fine beam section displacement: {f(abs(fine['section_mean_uz_mm']),7)} mm. Fine beam FE/CAD volume error: {f(fine['volume_relative_error']*100,4)}%. Worst force/moment balance residual: {f(max(max(x['force_balance_relative'],x['moment_balance_relative']) for x in allcases)*100,5)}%. All element Jacobians are positive: {all(x['minimum_det_jacobian']>0 for x in fem.get('levels',[]))}.",size=9.5)
    w.p('Limits are10% stress change,5% displacement change,0.5% beam volume error, positive Jacobians,0.5% equilibrium residual and15% Euler comparison difference. Under gravity, the reaction audit subtracts consistent applied DLOAD nodal forces from CalculiX RF before checking equilibrium [M1].',size=9.5)
    w.p('The ZIP retains full raw stress/displacement fields for the six fine-bracket cases and one fine-beam case. Coarser meshes retain input decks, meshes, logs, metrics and raw-output SHA-256 values; their fields can be regenerated. fem/retained_evidence.json records this scope explicitly.',size=9.5)
    w.page();w.h('Purchased parts and historical cost basis')
    w.p('The BOM uses exact catalogue identities and retained quotes dated17 November2026. Supplier dimensions and evidence were retrieved again for v1. The prices below remain historical; confirm final price, tax, minimum order and delivery before procurement. Current availability is not inferred from generic page templates.')
    with (r/'bom.csv').open() as ff:rows=list(csv.DictReader(ff))
    purchased=[x for x in rows if x['category']=='purchased']
    w.table(['Part','Used','Buy','Unit quote','Purchase cost'],[[x['part_number'],x['quantity_used']+' '+x['usage_unit'],x['purchase_quantity'],x['currency']+' '+f(float(x['unit_price']),2),x['currency']+' '+f(float(x['purchase_cost']),2)] for x in purchased],[2.3,1.2,.5,1.25,1.65],9)
    for x in purchased:w.link(x['part_number']+'  '+x['supplier'],x['purchase_url'])
    w.table(['Currency','Cash purchases','Base consumed','With all coupons'],[[cur,f(bom.get('cash_purchases_by_currency',{}).get(cur),2),f(bom.get('base_consumed_by_currency',{}).get(cur),2),f(bom.get('with_all_coupons_consumed_by_currency',{}).get(cur),2)] for cur in ['USD','EUR','GBP']],[1.2,1.9,1.9,1.9],10)
    w.p(f"Two brackets use{f(bom.get('two_brackets_mass_g'),2)} g of PETG; the five optional v1 coupons add{f(bom.get('five_coupons_mass_g'),2)} g. Both allocations use the same1 kg spool. The CSV's printed allocation rows are not counted again in purchase totals. Consumed beam cost uses400/609.6 of the stock purchase.")
    w.p('Currencies are kept separate. Taxes, shipping, customs, cutting, tools, energy, labor, support material and failed prints need additional allowance. Historical minimum orders explain46 unused anchors and21 unused sleeves.',size=10)
    w.page();w.h('CI execution requirements and saved feedback')
    w.p('The CI entry point runs the documented stages and writes a separate full stdout/stderr log. Each check reports its requirement IDs, observed value, criterion, status, evidence paths and next action. Missing software, omitted stages, stale hashes and execution errors cannot produce a passing engineering release.')
    w.table(['Artifact','Purpose'],[['logs/ci_<run_id>.log','Commands, versions, start/end times, durations, stdout/stderr and exit status'],['results/ci_summary.json','Structured current result and requirement coverage'],['results/selftest_summary.json','Functional CI and deliberate-defect test results'],['results/next_iteration.md','Actionable changes and evidence needed for the next version'],['AI_REFERENCE.md','Short guide to authoritative files, layout, requirements and commands']], [2.6,4.3],9.5)
    w.p('The test-system checks include deliberate geometric defects and missing/stale artifacts or failed solver behavior. A local execution confirms the CI commands operate in this environment. A hosted GitHub Actions run is not claimed until a repository workflow actually runs. The latest saved CI summary is authoritative for run counts and stage timing.',size=10)
    w.p('Saved CI self-test result: test_system_functional='+str(selftest.get('test_system_functional',False)).lower()+', exit_code='+str(selftest.get('exit_code','pending'))+'. The separate self-test log and summary preserve the executed negative controls. This functional result is distinct from design acceptance.',bold=True,size=10)
    w.p('Run from the extracted project root using the documented dependency versions:',size=10)
    w.code('python3 scripts/run_ci.py --mode audit\npython3 scripts/run_ci.py --mode full\npython3 scripts/run_ci.py --mode selftest\npython3 scripts/package_project.py --verify')
    w.p('To regenerate this report, run scripts/build_bom.py, scripts/build_report.py and scripts/render_report.py. scripts/build_native_report_plan.py prepares the native Google Docs content plan. PDF rendering needs LibreOffice on PATH; optional page PNG export also needs pdftoppm. Inspect every regenerated page before release.',size=9.5)
    w.table(['Requirement group','Verification path'],[['R01 R19','Frozen archive and reconstruction/source provenance'],['R02 R03 R04 R15','Native CAD, independent fit and hardware checks; physical records'],['R05 R08 R10 R13','Analytical screens, CalculiX results, convergence and physical load qualification'],['R06 R09','Source evidence and BOM with explicit price basis'],['R07 R11 R12','Native Google Doc, FreeCAD geometry and Gmsh STL provenance'],['R14 R16 R17 R18','Executable tests, CI controls, saved logs, requirement map and AI reference']], [1.7,5.2],9.5)
    w.page();w.h('Manufacture physical acceptance and source register')
    w.p('Resolve all numerical or geometric failures first. Inspect and finish-cut the tube, measure both openings and select suitable fit coupons. Initial print references are dry PETG, flange wall face on the bed,0.2 mm layers and100% infill; qualify the actual printer and process. Inspect the root, ribs, bores and sleeve projection. Qualify the concrete and follow the manufacturer drilling, cleaning and torque procedure. Detailed steps are in manufacturing/PRINT_AND_ASSEMBLY.md.')
    w.p('The proposed30 N assembly proof requires an agreed controlled test setup. Record direction, position, duration, deflection, residual movement and inspection findings. Sustained service loading and operating environment need separate qualification. Put genuine observations, operator, date and supporting files in config/physical_acceptance.json; null records stay BLOCKED.',size=10)
    w.p('Source files and extracted text are retained under evidence/ with URL, retrieval date and SHA-256. The archived v0 report is historical context; it is never evidence that a v1 FEM run occurred.',size=10)
    titles={'S1':'Online Metals23437 catalogue and section','S2':'Online Metals aluminum tolerances','S3':'Online Metals tolerance overview','S4':'Hydro6061 extrusion data sheet','S5':'Online Metals6061 physical properties','S6':'Prusament PETG technical data','S7':'Prusament PETG Jet Black spool','S8':'fischer564572 dimensions and installation','S9':'fischer permissible anchor load table','S10':'Accu EN1A sleeve catalogue','S11':'Accu M6 retention washer catalogue','S12':'Smiths EN1A generic properties','S13':'Klium fischer564572 distributor listing','S14':'ETA19/0520 full anchor assessment'}
    for s in sources['sources']:w.link(s['id']+'  '+titles.get(s['id'],s['purpose']),s['url'])
    w.link('M1  CalculiX manual section6.11.5 on RF; method verified with actual2.23 results','https://www.dhondt.de/ccx_2.13.pdf')
    w.link('M2  Gmsh official API and mesh documentation','https://www.gmsh.info/doc/texinfo/')
    w.p('Release decision: v1 supplies a reproducible reconstruction and a test system for the next iteration. Engineering release remains unapproved while any numerical, fit or physical acceptance gate is unresolved.',bold=True,size=10)
    (r/'report').mkdir(exist_ok=True);w.save()
    tracked=['requirement.md','frozen_requirements.sha256','config/design.json','config/physical_acceptance.json','cad/geometry_manifest.json','scripts/calculate.py','scripts/check_geometric_fit.py','scripts/run_fem.py','scripts/render_fem.py','scripts/build_bom.py','scripts/build_report.py','scripts/render_report.py','results/fem_render.json','results/stress_surface_data.json.xz','bom.csv','manufacturing/PRINT_AND_ASSEMBLY.md','evidence/source_manifest.json','evidence/solver_method_sources.json','evidence/calculix_rf_method.md','evidence/v0_report_export.docx']+w.images
    tracked += [p.relative_to(r).as_posix() for p in sorted((r/'fem').rglob('*')) if p.is_file() and any(p.name.endswith(ext) for ext in ['.inp','.inp.xz','.inc.xz','.frd.xz','.dat.xz','.solver.log','.log','.json'])]
    fem_metric_keys=['part','label','size_mm','nodes','elements','minimum_det_jacobian','FE_volume_mm3','CAD_volume_mm3','volume_relative_error','max_vm_bound_MPa','max_principal_abs_bound_MPa','max_displacement_bound_mm','max_nodal_vm_MPa','max_IP_vm_MPa','max_displacement_mm','section_mean_uz_mm','section_node_count']
    canonical_fem_levels=[{k:level[k] for k in fem_metric_keys if k in level} for level in fem.get('levels',[])]
    snapshot={'schema':'v1-report-source-snapshot','draft':draft,'static_file_hashes':{p:sha(r/p) for p in tracked if (r/p).exists()},'calculation_values':vals,'fit_checks':[dict((k,c.get(k)) for k in ['id','status','observed','criterion']) for c in fit.get('checks',[])],'FEM_checks':[dict((k,c.get(k)) for k in ['id','status','observed','criterion']) for c in fem.get('checks',[])],'FEM_levels':canonical_fem_levels,'BOM_metrics':{k:bom.get(k) for k in ['two_brackets_mass_g','five_coupons_mass_g','cash_purchases_by_currency','base_consumed_by_currency','with_all_coupons_consumed_by_currency']},'CI_selftest_functional':selftest.get('test_system_functional'),'policy':'Static source bytes and canonical engineering metrics are captured; mutable CI summaries and timestamps are not report prerequisites.'}
    (r/'report/source_snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    receipt={'schema':'v1-report-build','draft':draft,'source_hashes':snapshot['static_file_hashes'],'source_snapshot_sha256':sha(r/'report/source_snapshot.json'),'native_equations':22,'images':w.images,'numerical_status':num_state,'fit_status':fit_state,'physical_status':'BLOCKED','ci_counts_policy':'Latest results/ci_summary.json and logs are authoritative; report does not duplicate mutable final artifact counts.','outputs':{'report/report.md':sha(r/'report/report.md'),'report/report.docx':sha(r/'report/report.docx')}}
    (r/'report/build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'draft':draft,'native_equations':22,'figures':len(w.images),'numerical_status':num_state,'fit_status':fit_state},indent=2))
if __name__=='__main__':main()
