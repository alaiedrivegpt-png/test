#!/usr/bin/env python3
"""Orthographic dimensioned views from actual FreeCAD tessellation."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgb
ROOT=Path(__file__).resolve().parents[1]

def project_meshes(ax,items,view=(.45,-1,.35),front=False):
    view=np.array(view,dtype=float);view/=np.linalg.norm(view)
    right=np.cross(np.array([0.,0.,1.]),view);right/=np.linalg.norm(right)
    up=np.cross(view,right)
    if front:right=np.array([0.,1.,0.]);up=np.array([0.,0.,1.]);view=np.array([1.,0.,0.])
    light=np.array([.6,-.5,1.]);light/=np.linalg.norm(light)
    polys=[];colors=[];depth=[]
    for data,color,alpha in items:
        v=np.asarray(data['vertices']);f=np.asarray(data['faces']);tri=v[f]
        n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);norm=np.linalg.norm(n,axis=1);n=n/np.maximum(norm[:,None],1e-14)
        shade=.55+.45*np.maximum(n@light,0)
        rgb=np.array(to_rgb(color));rgba=np.column_stack([shade[:,None]*rgb, np.full(len(tri),alpha)])
        xy=np.stack([tri@right,tri@up],axis=2)
        polys.extend(xy);colors.extend(rgba);depth.extend(tri.mean(axis=1)@view)
    order=np.argsort(depth)
    polys=np.asarray(polys)[order];colors=np.asarray(colors)[order]
    ax.add_collection(PolyCollection(polys,facecolors=colors,edgecolors='none',antialiased=False))
    allxy=polys.reshape(-1,2);lo=allxy.min(axis=0);hi=allxy.max(axis=0);pad=.04*(hi-lo)
    ax.set_xlim(lo[0]-pad[0],hi[0]+pad[0]);ax.set_ylim(lo[1]-pad[1],hi[1]+pad[1]);ax.set_aspect('equal');ax.axis('off')

def main(root):
    d=json.loads((root/'cad/preview_mesh.json').read_text());out=root/'drawings';out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    fig=plt.figure(figsize=(10,4.2),facecolor='white');ax=fig.add_axes([.035,.105,.93,.78])
    items=[(d['bracket'],'#168c94',1),(d['right_bracket'],'#168c94',1),(d['beam'],'#aabcc9',.5)]
    items.extend((v,'#6b7782',1) for k,v in d.items() if k.startswith(('sleeve','washer')))
    project_meshes(ax,items,view=(.30,-1,.18))
    fig.text(.035,.945,'Beam wall mount v1',fontsize=18,fontweight='bold',color='#152d3d')
    fig.text(.035,.885,'Actual FreeCAD geometry  |  Tube transparent; sleeves and retention washers shown',fontsize=9,color='#465d70')
    fig.text(.035,.035,'Beam 400 mm  •  Wall bearing-face spacing 431.6 mm  •  End engagement 30 mm',fontsize=11,color='#152d3d')
    fig.savefig(out/'assembly.png',dpi=180);plt.close(fig)
    fig=plt.figure(figsize=(11.5,7),facecolor='white');ax=fig.add_axes([.035,.15,.43,.67]);project_meshes(ax,[(d['bracket'],'#168c94',1)],view=(1,-1,.45))
    fig.text(.04,.94,'Printed bracket v1',fontsize=22,fontweight='bold',color='#152d3d');fig.text(.04,.88,'FreeCAD solid with eight-edge 2 mm root fillet and four sacrificial fit ribs',fontsize=11,color='#465d70')
    ax2=fig.add_axes([.53,.16,.42,.64]);project_meshes(ax2,[(d['bracket'],'#77b5ba',1)],front=True)
    ax2.set_xlim(-46,55);ax2.set_ylim(-85,85)
    def dim(p,q,text,offset=(0,0),rotation=0):
        ax2.annotate('',xy=p,xytext=q,arrowprops={'arrowstyle':'<->','color':'#243e50','lw':.8})
        mid=((p[0]+q[0])/2+offset[0],(p[1]+q[1])/2+offset[1]);ax2.text(*mid,text,ha='center',va='center',fontsize=9,rotation=rotation,color='#243e50',bbox={'facecolor':'white','edgecolor':'none','pad':1})
    dim((-38,-75),(-38,75),'150 mm',rotation=90);dim((-30,-81),(30,-81),'60 mm',offset=(0,-1));dim((39,-60),(39,60),'120 mm pitch',rotation=90)
    fig.text(.05,.075,'Plate at bolts: 7.8 mm  |  Reinforced center: 13.8 mm  |  Sleeve holes: Ø18.6 mm',fontsize=11,color='#152d3d')
    fig.text(.05,.035,'Plug core: 31.55 mm  |  Rib envelope: 31.85 mm  |  Projection: 32 mm  |  Root relief: 2 mm',fontsize=11,color='#152d3d')
    fig.savefig(out/'bracket_detail.png',dpi=180);plt.close(fig)
    print('Created actual-CAD orthographic assembly and bracket views.')
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);main(ap.parse_args().root.resolve())
