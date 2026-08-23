## DC Power Flow

`DCPowerFlow` implements the linear DC power-flow approximation used by the
`DCPowerFlow` method. The implementation is in
`dcpf/solver.py` and uses unit voltage magnitudes, fixed reference-bus angles,
and a sparse linear solve for the remaining bus angles.

The solver does not solve reactive power or voltage magnitudes. Its active
power convention is positive for generation and negative for load.

### Data preparation

`DCPowerFlow.run` first converts the input into a `ParsedAnaredeSystem` using
`_as_parsed_system`. It accepts:

- an existing `ParsedAnaredeSystem`;
- its underlying infrasys `System`;
- a PWF path; or
- an NTW path.

`build_power_flow_case` then creates `BusData` and `BranchData` objects. For
each bus, the scheduled active-power injection is:

$$
P_i = \frac{P_{g,i} - P_{l,i}}{S_{\mathrm{base}}}
$$

The numerical case also supplies the bus numbering, reference-bus types,
initial reference angles, branch reactances, tap ratios, phase shifts, and
system base power.

### Reference buses and islands

The AC `build_ybus` function is used to identify disconnected islands. If an
island has no reference bus, `assign_island_reference_buses` selects a PV bus
with the largest scheduled generation, or the first available bus when no PV
bus exists. The selected bus is changed to a reference bus before the DC
matrix is assembled.

### DC network formulation

For a branch $k$ between buses $i$ and $j$, with series reactance $x_k$ and
tap ratio $\tau_k$, the branch susceptance used by `_build_dc_matrix` is:

$$
b_k = \frac{1}{x_k\tau_k}
$$

The matrix is assembled by adding the branch contribution:

$$
B_{ii} \mathrel{+}= b_k, \qquad
B_{jj} \mathrel{+}= b_k,
$$

$$
B_{ij} \mathrel{-}= b_k, \qquad
B_{ji} \mathrel{-}= b_k.
$$

Thus, the matrix used here is the series-reactance DC matrix. It is not the
full AC $-\operatorname{Im}(Y_{\mathrm{bus}})$ matrix because line charging,
shunts, and conductance are excluded from the linear angle solve.

For a branch phase shift $\phi_k$, `_phase_shift_injections` forms the
equivalent active-power injection vector $h$:

$$
h_i \mathrel{+}= b_k\phi_k, \qquad
h_j \mathrel{-}= b_k\phi_k.
$$

The branch active-power relation is:

$$
P_{ij} = b_k(\theta_i - \theta_j - \phi_k).
$$

Therefore, the full linear system is:

$$
B\theta = P + h.
$$

### Reduced angle solve

`_solve_angles` separates the reference buses $r$ from the non-reference buses
$n$. Reference angles are taken from the parsed case and remain fixed. The
reduced system is:

$$
B_{nn}\theta_n = P_n + h_n - B_{nr}\theta_r.
$$

The non-reference angles are solved with SciPy's sparse `spsolve` function.
Branches with zero reactance raise a `ValueError`, since their DC
susceptance would be undefined.

The complex voltage used for subsequent reporting is reconstructed with unit
magnitude:

$$
V_i = e^{j\theta_i}.
$$

### Lossless branch results

When `lossy_flows=False`, `_calculate_lossless_branch_results` reports the
classical DC branch flow:

$$
P_{ij} = S_{\mathrm{base}}
\frac{\theta_i - \theta_j - \phi_k}{x_k\tau_k}.
$$

The reverse terminal flow is the negative of the forward flow:

$$
P_{ji} = -P_{ij}, \qquad P_{\mathrm{loss},k}=0.
$$

Reactive flows are reported as zero. Branch loading is calculated from the
absolute flow and the branch rating:

$$
\operatorname{loading}_k =
100\frac{|P_{ij}|}{S_{\mathrm{rating},k}}.
$$

### Lossy branch results

When `lossy_flows=True`, `calculate_branch_results` uses the reconstructed
unit-magnitude complex voltages and the branch admittance model. For a branch
with series admittance $y_k=1/(r_k+jx_k)$, charging susceptance $b_{c,k}$, and
complex tap $t_k=\tau_ke^{j\phi_k}$, the terminal currents are:

$$
I_{ij} = \frac{y_k + j b_{c,k}/2}{|t_k|^2}V_i
		 - \frac{y_k}{t_k^*}V_j,
$$

$$
I_{ji} = -\frac{y_k}{t_k}V_i
		 + \left(y_k + j b_{c,k}/2\right)V_j.
$$

Terminal complex powers and branch losses are then:

$$
S_{ij}=V_iI_{ij}^*S_{\mathrm{base}}, \qquad
S_{ji}=V_jI_{ji}^*S_{\mathrm{base}},
$$

$$
P_{\mathrm{loss},k}=\operatorname{Re}(S_{ij}+S_{ji}).
$$

This mode changes branch-flow reporting and loss calculation; it does not
replace the linear DC angle solve with a nonlinear AC solve.

### Slack injection and mismatch

`_branch_net_injections` sums each terminal flow at its incident bus. The
non-reference bus injections remain scheduled, while each reference-bus
injection is replaced by the corresponding solved network injection. This
balances the lossless DC network exactly and accounts for reported losses in
lossy mode.

`_maximum_mismatch` compares the final bus injections with the net branch
injections:

$$
\epsilon_P = \max_i\left|P_i - P_{i,\mathrm{branch}}\right|.
$$

The result is represented by one `IterationPowerFlowResult` entry because the
DC method is a direct linear solve rather than an iterative nonlinear method.

### Results and export

`_calculate_bus_results` creates unit-magnitude bus results with the solved
angles and active injections. `apply_power_flow_result` attaches those values
to the parsed components, and `build_component_results` creates the shared
typed result model used by the AC solvers and Excel exporter.

```python
from o_grid import DCPowerFlow, ExportSolution

run = DCPowerFlow(lossy_flows=True).run(parsed_system)

ExportSolution(
	system=run.system,
	format="excel",
	output_path="case_solution_dcpf.xlsx",
)
```
