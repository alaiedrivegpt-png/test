# CadQuery and Open CASCADE geometric fit audit

Execution complete: **True**. Nominal geometry pass: **True**. Physical fit qualified: **False**.

| Check | Status | Observation and next action |
| --- | --- | --- |
| geometry:valid:beam_400mm | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:bracket | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:bracket_structural_core_only | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:bracket_added_ribs | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:bracket_right | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:bracket_right_structural_core_only | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:sleeves | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:retention_washers | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:anchor_shanks_simplified | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:valid:assembly | PASS | CadQuery STEP import and OCCT solid/volume validity compared with FreeCAD manifest. |
| geometry:beam_dimensions | PASS | Beam length, outside section and position measured from delivered STEP. |
| geometry:catalogue_profile | PASS | Actual STEP curved faces and flat walls match the selected rounded catalogue section. |
| fit:right_printable_pose | PASS | Actual delivered assembly instance agrees with the required transform. |
| fit:right_core_pose | PASS | Actual delivered assembly instance agrees with the required transform. |
| assembly:actual_instance:beam_400mm | PASS | The assembly STEP contains the actual intended part in its tested pose. |
| assembly:actual_instance:bracket | PASS | The assembly STEP contains the actual intended part in its tested pose. |
| assembly:actual_instance:bracket_right | PASS | The assembly STEP contains the actual intended part in its tested pose. |
| fit:engagement_and_relief | PASS | Both imported bracket ends seat at the specified engagement and root-relief distances. |
| fit:left:core_collision | PASS | Structural-core collision checked by OCCT Boolean common on imported solids. |
| fit:left:core_clearance | PASS | Minimum core-to-tube surface clearance measured directly by OCCT. |
| fit:right:core_collision | PASS | Structural-core collision checked by OCCT Boolean common on imported solids. |
| fit:right:core_clearance | PASS | Minimum core-to-tube surface clearance measured directly by OCCT. |
| fit:separate_sacrificial_ribs | PASS | Printable-minus-core geometry matches the separately exported rib solids. |
| fit:rib_region_bounds | PASS | Sacrificial ribs lie only in the explicit four thin bands and insertion length. |
| fit:left:intentional_interference | PASS | Nonzero nominal press-fit interference is confined to separately identified sacrificial ribs. |
| fit:right:intentional_interference | PASS | Nonzero nominal press-fit interference is confined to separately identified sacrificial ribs. |
| fit:left:sampled_insertion_path | PASS | Pure axial core insertion/withdrawal sampled at <=1 mm steps from unengaged to seated; physical rib deformation is excluded. |
| fit:right:sampled_insertion_path | PASS | Pure axial core insertion/withdrawal sampled at <=1 mm steps from unengaged to seated; physical rib deformation is excluded. |
| hardware:mount_holes | PASS | Actual cylindrical bores have the required diameter, centerline and pitch. |
| hardware:actual_solids | PASS | Imported sleeves, washers and simplified M6 shanks have nominal diameters and no forbidden plate collision. |
| hardware:positions:sleeves | PASS | Every imported modeled hardware instance has the required axial length, bolt center and left/right pose. |
| assembly:actual_hardware:sleeves | PASS | Assembly STEP contains all four hardware components in their independently checked poses. |
| hardware:positions:retention_washers | PASS | Every imported modeled hardware instance has the required axial length, bolt center and left/right pose. |
| assembly:actual_hardware:retention_washers | PASS | Assembly STEP contains all four hardware components in their independently checked poses. |
| hardware:positions:anchor_shanks_simplified | PASS | Every imported modeled hardware instance has the required axial length, bolt center and left/right pose. |
| assembly:actual_hardware:anchor_shanks_simplified | PASS | Assembly STEP contains all four hardware components in their independently checked poses. |
| hardware:tolerance_stack | PASS | Supplier hardware tolerance stack screened against nominal printed plate; actual printed dimensions remain unmeasured. |
| fit:catalogue_tolerance_qualification | BLOCKED | The fixed nominal plug does not fit every allowed catalogue opening; actual purchased tube dimensions are not measured. Next: Measure both flats and corners at both tube ends, select/rebuild coupons and adapt plug core/rib dimensions to those observations; rerun this checker. |
| fit:physical_press_fit | BLOCKED | CAD does not establish insertion force, rib crushing, retention, printed shrinkage or creep. Next: Print qualified material, measure openings and coupons, record insertion/retention/proof and environmental tests before release. |
