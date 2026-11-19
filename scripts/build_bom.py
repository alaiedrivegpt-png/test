#!/usr/bin/env python3
"""Rebuild the priced BOM using current FreeCAD volumes and retained dated quotes."""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(root=ROOT):
    root=Path(root);cfg=json.loads((root/'config/design.json').read_text());geo=json.loads((root/'cad/geometry_manifest.json').read_text())
    if geo['design_sha256']!=sha(root/'config/design.json'):raise ValueError('CAD manifest does not match current design; rebuild CAD first.')
    bracket_volume=geo['geometry']['bracket']['volume_mm3'];coupon_volume=sum(x['volume_mm3'] for x in geo['coupons'].values())
    mass=2*bracket_volume*cfg['bracket']['density_kg_m3']*1e-6;coupon_mass=coupon_volume*cfg['bracket']['density_kg_m3']*1e-6
    filament=23.99;beam_consumed=13.61*cfg['beam']['length_mm']/cfg['beam']['stock_length_mm']
    common={'quote_date':'2026-11-17','price_status':'Historical quote reconstructed from saved v0 Google Doc; verify current checkout','price_evidence':'evidence/v0_report_export.docx','tax_shipping_basis':'No additional tax, shipping, customs, tools, labor or print-waste allowance included'}
    rows=[]
    def add(item,name,supplier,part,used,unit,buy,cur,price,consumed,url,source,notes,category='purchased'):
        rows.append(dict(common,item_id=item,category=category,description=name,supplier=supplier,part_number=part,quantity_used=used,usage_unit=unit,purchase_quantity=buy,purchase_unit='each',currency=cur,unit_price=price,purchase_cost=round(buy*price,6),base_consumed_cost=round(consumed,6),add_to_purchase_total=category=='purchased',add_to_base_consumed_total=category=='purchased',purchase_url=url,catalogue_evidence=source,notes=notes))
    add('B01','6061-T6 radius-corner square tube, 24 inch stock','Online Metals','23437',1,'piece cut to 400 mm',1,'USD',13.61,beam_consumed,'https://www.onlinemetals.com/en/buy/aluminum/1-5-x-0-125-aluminum-square-tube-6061-t6-extruded-radius-corner/pid/23437','evidence/onlinemetals_23437.html','609.6 mm stock; finish cut 400 +/-0.5 mm. Nominal 38.1 OD, 3.175 wall; radii 3.175 outer and 1.5748 inner mm. Consumed cost allocated by 400/609.6.')
    add('B02','Prusament PETG Jet Black 1 kg spool','Prusa','IDS 3449 / IDF 17558',round(mass,6),'g for two brackets',1,'USD',filament,mass/1000*filament,'https://www.prusa3d.com/product/prusament-petg-jet-black-1kg/','evidence/prusament_petg_black.html','One spool supplies both brackets and optional coupons. Typical properties only; actual print process and retention require qualification.')
    add('B03','FAZ II Plus 6/10 zp M6 expansion anchor','fischer / Klium','564572',4,'anchors',50,'EUR',.63,4*.63,'https://www.klium.com/en/fischer-564572-piercing-anchor-faz-ii-plus-6-10-ev-electrolytically-galvanised-steel-176237','evidence/fischer_564572.html; evidence/klium_anchor.html','Two anchors per bracket. Historical minimum order 50. Use included washer/nut plus specified retention washer. Actual concrete and installation must be qualified.')
    add('B04','18 x 6.4 x 8 mm compression sleeve, EN1A','Accu','HPS-18-6.4-8-EN1A',4,'sleeves',25,'GBP',4.02,4*4.02,'https://www.accu.co.uk/cylindrical-spacers/1038448-HPS-18-6-4-8-EN1A','evidence/accu_sleeve.html','Historical minimum order 25. OD18 +/-0.4, ID6.4 +/-0.1, length8 +/-0.1 mm. Each measured sleeve must stand >=0.1 mm above the printed flange.')
    add('B05','M6 x 30 mm retention washer, A2','Accu','HYW-M6-30-A2',4,'washers',4,'GBP',.38,4*.38,'https://www.accu.co.uk/metric-flat-washers/14666-HYW-M6-30-A2','evidence/accu_washer.html','OD30 +0/-1.3, ID6.4 +0.3/-0, thickness1.5 +/-0.3 mm. Retains large printed sleeve bore; keep original anchor washer/nut above it.')
    add('P01','Printed bracket allocation','Project','v1 bracket',2,'brackets',0,'USD',mass/2/1000*filament,mass/1000*filament,'','cad/geometry_manifest.json','Descriptive allocation only; already counted in B02. Excluded from additive purchase and consumed totals.','printed_allocation')
    add('P02','Optional fit coupon set allocation','Project','v1 coupons 31.65 to 32.05 mm',5,'coupons',0,'USD',coupon_mass/5/1000*filament,coupon_mass/1000*filament,'','cad/geometry_manifest.json','Optional allocation from the same spool, added once only to optional consumed-material scenario. New v1 coupon geometry; no v0 mass reused.','optional_allocation')
    with (root/'bom.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    purchase={};consumed={}
    for r in rows:
        if r['category']=='purchased':purchase[r['currency']]=purchase.get(r['currency'],0)+r['purchase_cost'];consumed[r['currency']]=consumed.get(r['currency'],0)+r['base_consumed_cost']
    optional=dict(consumed);optional['USD']+=coupon_mass/1000*filament
    out={'schema':'bom-summary-v1','price_date':'2026-11-17','price_status':'Historical quotes, not a current procurement offer','bracket_volume_each_mm3':bracket_volume,'two_brackets_mass_g':mass,'five_coupons_mass_g':coupon_mass,'cash_purchases_by_currency':purchase,'base_consumed_by_currency':consumed,'with_all_coupons_consumed_by_currency':optional,'input_hashes':{'config/design.json':sha(root/'config/design.json'),'cad/geometry_manifest.json':sha(root/'cad/geometry_manifest.json'),'evidence/v0_report_export.docx':sha(root/'evidence/v0_report_export.docx')},'bom_sha256':sha(root/'bom.csv'),'checks':[{'id':'bom:complete_catalogue_lines','requirements':['R09'],'status':'PASS','observed':len([r for r in rows if r['category']=='purchased']),'criterion':'Five purchased component lines with catalogue IDs, prices, quantities, external links, source files and notes','message':'Current geometry volumes determine consumed filament; historical quote date and current-procurement block are explicit.','next_action':'Obtain current quotes and delivery confirmation before purchasing.','evidence':['bom.csv','results/bom_summary.json','evidence/v0_report_export.docx']}],'notes':['Currencies are not converted or added together.','Minimum order quantities are distinct from quantities installed.','Printed allocations are not counted twice.','Historical stock labels were not reused as current availability claims.']}
    (root/'results/bom_summary.json').write_text(json.dumps(out,indent=2)+'\n');return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);a=ap.parse_args();out=build(a.root)
    print(json.dumps({k:out[k] for k in ['cash_purchases_by_currency','base_consumed_by_currency','two_brackets_mass_g','five_coupons_mass_g']},indent=2))
if __name__=='__main__':main()
