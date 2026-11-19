# Next iteration feedback

Run: 20261119T212645_389218Z
Engineering release: **BLOCKED**
Test system functional: **True**
Counts: {'PASS': 208, 'FAIL': 0, 'BLOCKED': 14, 'ERROR': 0}
Full log: `logs/ci_20261119T212645_389218Z.log`

A passing test harness does not override failed geometry, analysis or physical evidence.

## Required actions

### geometric_fit:fit:catalogue_tolerance_qualification

Status: **BLOCKED**; requirements: R03, R15.
The fixed nominal plug does not fit every allowed catalogue opening; actual purchased tube dimensions are not measured.
Observed: `{"minimum_catalogue_opening_mm": 30.708600000000004, "nominal_core_mm": 31.55, "hypothetical_minimum_opening_collision_mm3": 1311.1048187999945, "all_catalogue_extremes_fit": false}`
Criterion: `"Actual measured tube opening and selected fit coupon must demonstrate geometric fit; nominal STEP PASS alone cannot approve the purchased lot."`
**Next action:** Measure both flats and corners at both tube ends, select/rebuild coupons and adapt plug core/rib dimensions to those observations; rerun this checker.
Evidence: `config/design.json`, `config/physical_acceptance.json`

### geometric_fit:fit:physical_press_fit

Status: **BLOCKED**; requirements: R03, R05, R15.
CAD does not establish insertion force, rib crushing, retention, printed shrinkage or creep.
Observed: `null`
Criterion: `"Authentic print, insertion, retention and sustained-load evidence."`
**Next action:** Print qualified material, measure openings and coupons, record insertion/retention/proof and environmental tests before release.
Evidence: `config/physical_acceptance.json`, `manufacturing/PRINT_AND_ASSEMBLY.md`

### physical:beam_length_mm

Status: **BLOCKED**; requirements: R02.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document beam length mm. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:beam_lot_certificate

Status: **BLOCKED**; requirements: R06.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document beam lot certificate. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:tube_openings_both_ends_mm

Status: **BLOCKED**; requirements: R03.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document tube openings both ends mm. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:selected_fit_coupon

Status: **BLOCKED**; requirements: R03.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document selected fit coupon. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:press_fit_insertion_and_retention

Status: **BLOCKED**; requirements: R03, R05.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document press fit insertion and retention. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:printed_process_and_material

Status: **BLOCKED**; requirements: R03, R05.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document printed process and material. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:actual_wall_and_anchor_installation

Status: **BLOCKED**; requirements: R04, R05.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document actual wall and anchor installation. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:sleeve_projection_all_four_mm

Status: **BLOCKED**; requirements: R04, R05.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document sleeve projection all four mm. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:assembly_30N_proof_test

Status: **BLOCKED**; requirements: R05.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document assembly 30N proof test. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:sustained_load_environment

Status: **BLOCKED**; requirements: R05.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document sustained load environment. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:current_procurement_quotes

Status: **BLOCKED**; requirements: R09.
No actual physical observation has been recorded.
Observed: `null`
Criterion: `"Authentic recorded measurement/test evidence"`
**Next action:** Perform and document current procurement quotes. Record observations, operator/date and evidence; simulation cannot approve this gate.
Evidence: `config/physical_acceptance.json`

### physical:provenance

Status: **BLOCKED**; requirements: R02, R03, R04, R05, R06.
A claimed physical pass lacks operator, date or evidence.
Observed: `null`
Criterion: `null`
**Next action:** Add genuine operator, date and retained evidence after actual qualification.
Evidence: `config/physical_acceptance.json`

