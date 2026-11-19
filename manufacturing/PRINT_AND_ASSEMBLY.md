# Printing assembly and physical qualification

## Scope

This is a reconstructed v1 prototype. Follow the current requirement audit and next-iteration feedback. Numerical and geometric results are conditional screens; manufacturing release needs genuine measurements and load evidence recorded in `config/physical_acceptance.json`.

## Prepare the purchased parts

1. Verify the exact purchased beam catalogue and material identification. Retain its lot certificate and inspect damage.
2. Cut and finish the tube to 400±0.5 mm. Deburr the edges without changing the contact profile unpredictably.
3. Measure both internal flat dimensions and the internal corner clearance at both ends. Measure the opposing wall spacing and the real substrate. The nominal design needs 431.6 mm between wall bearing faces.
4. Select an appropriate coupon. The five nominal coupon envelopes 31.65,31.75,31.85,31.95,32.05 mm do not cover the entire catalogue tolerance range. If they are unsuitable, revise the fit parameters from the measurements, regenerate all CAD/STL and rerun the complete CI. Do not force an oversized structural core into the tube.

## Print and qualify

Use dry, identified Prusament PETG. Place the flange wall face on the print bed, with local CAD x along the build direction. Initial process references are 0.2 mm layers and 100% infill; nozzle 250 °C/bed 80 °C follow the supplier's test specimen settings and require printer-specific qualification. Record actual printer, nozzle, temperatures, layer height, flow, cooling, material lot and storage.

Print fit coupons before brackets. Record dimensions and insertion/removal behavior. A CAD collision confined to the identified ribs is intentional and does not prove real insertion force, crushing, retained pressure or pull-out resistance. Verify appropriate core clearance and robust retention in the actual tube at both ends. Retain photographs and force measurements.

## Assemble and install

Use two identical printed brackets, four specified steel sleeves, four large retention washers and four specified fischer M 6 anchors. Keep the manufacturer's supplied anchor washer and nut in their prescribed positions; the modeled large washer is additional retention hardware.

Measure every steel sleeve and local printed plate thickness. Each sleeve must stand at least 0.1 mm proud of its printed plate so anchor tightening load bypasses the plastic. Nominal projection is 0.2 mm; this also creates clearance that the linear FEM attachment idealization does not fully model. Confirm washer coverage over the large hole and a complete installed fixture stack within the anchor's 10 mm limit.

Only the provisional solid C20/25 concrete wall is covered by the conditional anchor calculations. Verify wall thickness, edge distances, spacing, embedment, drill depth and the manufacturer's drilling, cleaning and tightening instructions. Use a calibrated torque method and retain installation evidence. Other wall materials need a new fastening design.

Seat each beam end 30 mm into its bracket beyond the 2 mm root relief. Do not create unintended structural-core collision by drawing misaligned parts together with anchor nuts. Confirm actual bracket seating, wall spacing, anchor access and final alignment.

## Required evidence before approval

A named competent operator must retain dated records for material/print qualification, both-end dimensions, coupon choice, insertion and retention, sleeve projections, actual wall/anchors and complete assembly loading. The proposed 30 N proof level is three times the 10 N service force; a competent test plan must define directions, load footprint, duration, instrumentation and acceptable damage/permanent displacement. A short proof test does not establish long-term PETG creep or environmental life. Qualify sustained loading and the intended temperature, moisture and exposure conditions separately.

Enter measured values and real evidence paths into the physical acceptance record. Do not convert a simulation result into a physical PASS. Preserve original observations and failures for the next version.
