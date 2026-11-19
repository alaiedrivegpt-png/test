# CalculiX RF interpretation

Source: Guido Dhondt, *CalculiX CrunchiX User's Manual*, version 2.13, section 6.11.5, printed pages 288–291.

Official URL: https://www.dhondt.de/ccx_2.13.pdf

Retrieved and checked: 19 November 2026.

Short source quotation:

> With RF you get the sum of all external forces in a node.

The section explains that RF combines the reaction and the applied nodal contribution. Distributed element loads can contribute to that applied nodal term. To recover the support reaction used in a global equilibrium check, the v1 pipeline subtracts the consistent applied gravity contribution at the restrained degrees of freedom.

This is a method reference to the published 2.13 manual, not a claim that the project used solver 2.13. The executed v1 solver is CalculiX 2.23; its actual force and moment residuals, input/output hashes, solver logs and independent integration checks are recorded in the project results.

For straight C3D10 geometry and constant body force, the integrated scalar shape-function weights are −V/20 at each of the four corner nodes and V/5 at each of the six midside nodes. The ten weights sum to V. This identity is tested independently in the Python test suite.
