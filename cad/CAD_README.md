# Reconstructed v1 CAD

The native FreeCAD documents and STEP files in this directory were newly built for v1. They are not recovered v0 geometry. The retained report and conversation established the main dimensions; the rib cross section and coupon details are explicit v1 reconstruction choices.

## Authoritative geometry

`config/design.json` supplies dimensions. `scripts/build_cad.py` reconstructs the parts with FreeCAD 1.0.0. Native FCStd files retain named geometric construction stages and numeric parameter records. Change the JSON and regenerate; the stage shapes are not represented as a fully constrained interactive sketch tree. STEP exports are the interface for independent CadQuery/Open CASCADE checks and Gmsh.

| File | Purpose |
| --- | --- |
| `bracket.FCStd` and `bracket.step` | Printable bracket, including sacrificial ribs |
| `bracket_structural_core_only.FCStd` and `.step` | Reinforced bracket without fit ribs; structural FEM input |
| `bracket_added_ribs.step` | Only material added outside the structural core; explicit allowed interference region |
| `bracket_right.step` and `bracket_right_structural_core_only.step` | Actual right-end assembly instances |
| `beam_400mm.FCStd` and `.step` | Purchased rounded-profile tube cut to 400 mm |
| `assembly.FCStd` and `.step` | Beam, both brackets, four sleeves, four retention washers and simplified shanks |
| `fit_coupons.FCStd` and five coupon STEP files | Nominal trial rib-envelope sizes; actual tube measurements may require other sizes |
| `sleeves.step` and `retention_washers.step` | Nominal purchased hardware geometry |
| `anchor_shanks_simplified.step` | Cylindrical M 6 shank envelopes, not detailed anchor mechanisms |
| `geometry_manifest.json` | Shape properties, reconstruction notes, versions and hashes |
| `preview_mesh.json` | Actual CAD tessellation used only for illustrations; printable STL comes from Gmsh |

## Coordinates and dimensions

All STEP coordinates are global millimetres. The left wall is x=0. The left plate occupies x=0 to 7.8; central reinforcement reaches x=13.8; the plug tip is x=45.8. The beam occupies x=15.8 to 415.8. The right wall is x=431.6. The right bracket is a 180-degree rotation about z followed by translation to the right wall. Both engagements are 30 mm with 2 mm root-relief space.

The purchased section has 38.1 mm outer flats,31.75 mm inner flats,3.175 mm outer corner radius and 1.5748 mm inner corner radius. The core has 31.55 mm flats with 3 mm corner chamfers. An eight-edge 2 mm root fillet joins the plug to the reinforced plate.

Each of four reconstructed triangular ribs is 1.2 mm wide at its embedded base, embedded 0.075 mm into the core, with maximum envelope 31.85 mm. Ribs run from x=16 to x=44.3. This provides nominal 0.05 mm radial interference with the selected tube; real deformation and retention are unqualified. The structural core has nominal 0.1 mm minimum clearance.

The simplified anchor shanks omit threads, nuts, the supplied small washer and the expansion mechanism. Geometry checks on those shanks verify passage only. Catalogue anchor capacity, torque and actual wall qualification remain separate.

## Commands

```bash
/usr/bin/python3 scripts/build_cad.py --root .
/usr/bin/python3 scripts/build_cad.py --root . --validate-only
python3 scripts/check_geometric_fit.py --root .
python3 -m unittest discover -s tests -p test_geometric_fit.py -v
```

The first command rebuilds CAD and changes frozen outputs. The second opens the current native files read-only and verifies their actual final solids against the manifest. The third independently imports current STEP solids into CadQuery/Open CASCADE; it does not import the FreeCAD generator.

A successful nominal geometric fit does not qualify the purchased/printed fit. The supplier tolerance envelope includes openings smaller than this fixed nominal core. Measure both tube ends and adapt the core/ribs/coupons before physical acceptance. Never use a nominal result to approve an unmeasured actual part.
