# v1 analytical calculations

Fresh calculations for reconstructed v1. Historical v0 FEM values are not used.

## Formulas

- **Self weight:** `W=Amax*L*rho*g*1e-9; q=W/L (rho in kg/m3, length in mm)`
- **Bracket selfweight bound:** `Vp_upper=plate_width*plate_height*(base_thickness+reinforcement)+rib_envelope^2*(plug_projection+root_fillet); Wp=Vp_upper*rho_p*g*1e-9`
- **Reaction envelopes:** `R_required=F+Wbeam+Wp; T_required=(F+Wbeam)*cmax*sqrt(2)+Wp*plate_width/2; Mt_required=Mmax+Me`
- **Beam shear and torsion:** `Am_lower=As(bmin-2*tmax,ri_max); tau_T=(F*cmax*sqrt(2))/(2*Am_lower*tmin); tau_V=1.5*(F+W)/(2*tmin*(bmin-2*tmin))`
- **Plug displacement:** `delta_p=R*ell^3/(3*Ep*Ip)+Mt*ell^2/(2*Ep*Ip)`
- **Plate strip:** `sigma_plate=(R*bolt_pitch/4)/(plate_width*plate_thickness^2/6)`
- **Rounded square area:** `As(b,r)=b^2-(4-pi)r^2`
- **Rounded square inertia:** `Is(b,r)=b^4/12-4*((b/2-r)^2*r^2*(1-pi/4)+(b/2-r)*r^3/3+r^4*(1/3-pi/16))`
- **Tube section:** `A=As(b,ro)-As(b-2t,ri); I=Is(b,ro)-Is(b-2t,ri)`
- **Beam moment:** `M=F*L/4+q*L^2/8; Me=F*cmax*sqrt(2)`
- **Beam stress:** `sigma_b=sqrt(2)*(M+Me)/Z; sigma_a=F/Amin; VM=sqrt((sigma_b+sigma_a)^2+3*(tau_T+tau_V)^2)`
- **Beam deflection:** `delta=F*L^3/(48*E*Imin)+5*q*L^4/(384*E*Imin)+Me*L^2/(8*E*Imin)`
- **Compression:** `Pe=pi^2*E*Imin/L^2; Pallow=min(Pe,yield*Amin)/3`
- **Plug:** `Ap=B^2-2*C^2; Ip=B^4/12-4*((C^2/2)*(B/2-C/3)^2+C^4/36)`
- **Plug stress:** `sigma=sqrt(2)*(R*ell+Mt)/Zp+R/Ap; tau=1.5*R/a^2+Tx/(0.208*a^3); VM=sqrt(sigma^2+3*tau^2)`
- **Local contact:** `Fc=R+Mt/(engagement-10); p=Fc/(10*(B-2*C)); sigmawall=(Fc*(bmax-2*tmin)/4)/(10*tmin^2/6)`
- **Anchor:** `N=R+(R*e+Mt)/s; V=R+Tx/s; Mb=V*(fixture+0.5*d)+R*e+Mt; U=N/700+V/4300+Mb/6285.714`
- **Sleeve preload:** `Fpre=Tinst/(K*d), K=0.15..0.25; compression=Fpre/Asleeve`

## Calculated values

| Quantity | Value |
| --- | --- |
| section_area_mm2 | 437.023063 |
| section_I_mm4 | 88514.405 |
| section_Amin_mm2 | 400.266803 |
| section_Amax_mm2 | 474.481258 |
| section_Imin_mm4 | 78669.2247 |
| section_Zmin_mm3 | 4061.91944 |
| beam_weight_upper_N | 5.21795453 |
| beam_moment_max_Nmm | 1262.47385 |
| eccentric_axial_moment_Nmm | 273.897812 |
| torsion_enclosed_area_lower_mm2 | 939.681053 |
| beam_torsion_shear_MPa | 0.0490409097 |
| beam_transverse_shear_MPa | 0.121840723 |
| beam_bending_stress_MPa | 0.534909092 |
| beam_global_vm_MPa | 0.633309662 |
| beam_local_wall_stress_MPa | 55.6944682 |
| beam_global_deflection_mm | 0.00428456014 |
| beam_nominal_euler_deflection_mm | 0.00284020424 |
| beam_nominal_weight_N | 4.80002009 |
| beam_euler_buckling_N | 333747.912 |
| beam_compression_allowable_N | 32021.3442 |
| beam_compression_utilization | 0.000312291699 |
| bracket_bounding_volume_mm3 | 158690.365 |
| bracket_weight_upper_N | 1.9764005 |
| required_bracket_force_N | 17.194355 |
| required_bracket_torsion_Nmm | 476.108459 |
| required_bracket_transverse_moment_Nmm | 1536.37166 |
| plug_area_mm2 | 977.4025 |
| plug_I_mm4 | 78630.4335 |
| plug_vm_MPa | 0.745511168 |
| plug_deflection_mm | 0.00942613336 |
| plate_strip_stress_MPa | 0.986193294 |
| contact_force_N | 100 |
| contact_bearing_pressure_MPa | 0.391389432 |
| anchor_tension_N | 40.9666667 |
| anchor_shear_N | 24.5833333 |
| anchor_bending_Nmm | 2833.125 |
| anchor_interaction | 0.514965296 |
| fixture_max_mm | 9.9 |
| preload_range_N | [5333.333333333333, 8888.88888888889] |
| sleeve_min_area_mm2 | 210.101863 |
| sleeve_compression_MPa | 42.3075206 |
| aluminum_allowable_MPa | 80 |
| PETG_allowable_MPa | 4.66666667 |

## Checks

| Check | Status | Observed | Limit |
| --- | --- | --- | --- |
| calc:beam_global_stress | PASS | 0.633309662 | 80 |
| calc:beam_local_wall_stress | PASS | 55.6944682 | 80 |
| calc:beam_displacement | PASS | 0.00428456014 | 1 |
| calc:beam_compression | PASS | 10 | 32021.3442 |
| calc:bracket_force_envelope | PASS | 17.194355 | 20 |
| calc:bracket_torsion_envelope | PASS | 476.108459 | 550 |
| calc:bracket_transverse_moment_envelope | PASS | 1536.37166 | 1600 |
| calc:plug_stress | PASS | 0.745511168 | 4.66666667 |
| calc:plug_displacement | PASS | 0.00942613336 | 1 |
| calc:plate_strip_stress | PASS | 0.986193294 | 4.66666667 |
| calc:bearing_pressure | PASS | 0.391389432 | 4.66666667 |
| calc:anchor_interaction | PASS | 0.514965296 | 1 |
| calc:fixture_thickness | PASS | 9.9 | 10 |

## Model limits

All quantities mm, N, MPa unless named otherwise.
Independent dimensional tolerance extremes form a conservative envelope.
PETG 14 MPa is a typical-data screening reference, not a qualified print allowable.
Closed-section torsion remains a thin-wall screening approximation; enclosed area uses the smallest tolerance-envelope inner void, conservatively below the median enclosed area.
Ribs carry no credited structural load. Contact patches, wall identity and torque load path require physical qualification.
Bracket selfweight uses an explicit bounding rectangular volume, not the historical v0 mass.
Preload/sleeve compression is an estimate; no qualified sleeve-bearing or washer-preload PASS is asserted.
