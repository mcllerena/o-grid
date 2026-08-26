# ACOPF Formulation Reference

This document describes the AC optimal power-flow formulation implemented by
the local `PowerModels.jl` reference at:

`power-simulator/references/PowerModels.jl`

The relevant implementation files are:

- `src/prob/opf.jl`: assembles the OPF problem.
- `src/form/acp.jl`: AC polar power-flow equations.
- `src/core/variable.jl`: decision variables and bounds.
- `src/core/constraint_template.jl`: shared voltage, angle, and thermal constraints.
- `src/core/objective.jl`: generation and flow-cost objectives.
- `src/core/base.jl` and `src/core/types.jl`: model dispatch and formulation types.

## 1. Approach Used by PowerModels.jl

PowerModels is a model-building framework. It does not implement one single
ACOPF algorithm. Instead, it combines:

1. A network problem, here `build_opf`.
2. A mathematical formulation, here `ACPPowerModel`.
3. A nonlinear optimizer supplied by the caller, for example Ipopt.

The public ACOPF entry point is:

```julia
solve_ac_opf(file, optimizer; kwargs...)
```

which dispatches to:

```julia
solve_opf(file, ACPPowerModel, optimizer; kwargs...)
```

Thus the reference is a nonlinear, nonconvex AC polar OPF solved directly by
an NLP solver. It is not a Newton-Raphson power flow, a residual least-squares
problem, or a convex relaxation.

## 2. ACOPF Problem

For a network with buses $i \in \mathcal{B}$, generators $g \in \mathcal{G}$,
and directed branch arcs $(i,j) \in \mathcal{A}$, the ACOPF is:

$$
\begin{aligned}
\min_{x}\quad & \sum_{g \in \mathcal{G}} c_g(p_g)
				 + \sum_{(i,j) \in \mathcal{A}} c_{ij}^{flow}(p_{ij},q_{ij}) \\
	ext{s.t.}\quad & \text{AC network equations} \\
				 & \text{generator, voltage, angle, and thermal limits}.
\end{aligned}
$$

The usual PowerModels OPF uses hard equalities and inequalities. If the
nonlinear solver returns an optimal point, that point is still only useful if
the equality residuals and inequality violations are within the solver's
termination tolerances.

## 3. Decision Variables

### Bus voltage

For every bus $i$ the ACP model creates:

$$
v_i \ge 0, \qquad \theta_i,
$$

where $v_i$ is voltage magnitude in per unit and $\theta_i$ is voltage angle
in radians. The complex voltage is:

$$
V_i = v_i e^{\mathrm{i}\theta_i}.
$$

The variable bounds come from the input data:

$$
v_i^{\min} \le v_i \le v_i^{\max}.
$$

### Generator dispatch

For each generator $g$:

$$
p_g^{\min} \le p_g \le p_g^{\max},
\qquad
q_g^{\min} \le q_g \le q_g^{\max}.
$$

The generator is connected to its bus through the bus power-balance equation.
Multiple generators at one bus are summed.

### Branch power

For each directed branch arc, PowerModels creates active and reactive flow
variables:

$$
p_{ij},\ q_{ij},\qquad p_{ji},\ q_{ji}.
$$

These variables are not independent physical approximations: the Ohm equations
below define them exactly from the voltage variables.

DC lines, storage, switches, and other devices add their own variables when
the corresponding problem builder includes them. The basic `build_opf` model
includes AC branches and DC-line power variables.

## 4. AC Bus Power Balance

PowerModels uses the convention that branch arc flows leave the bus. At every
bus $i$, active power balance is:

$$
\sum_{(i,j)\in\mathcal{A}_i} p_{ij}
 + \sum_{d\in\mathcal{D}_i} p_d
 =
\sum_{g\in\mathcal{G}_i} p_g
 - \sum_{s\in\mathcal{S}_i} p_s
 - \sum_{d\in\mathcal{L}_i} p_d^{load}
 - g_i v_i^2.
$$

Reactive power balance is:

$$
\sum_{(i,j)\in\mathcal{A}_i} q_{ij}
 + \sum_{d\in\mathcal{D}_i} q_d
 =
\sum_{g\in\mathcal{G}_i} q_g
 - \sum_{s\in\mathcal{S}_i} q_s
 - \sum_{d\in\mathcal{L}_i} q_d^{load}
 + b_i v_i^2.
$$

Here $g_i$ and $b_i$ are the bus shunt conductance and susceptance. The
implementation is `constraint_power_balance` in `src/form/acp.jl`. The
standard OPF builder calls it once for every bus.

## 5. Branch Ohm Equations

For a branch from bus $i$ to bus $j$, let:

- $g,b$: series conductance and susceptance;
- $g^{fr},b^{fr}$: from-side shunt terms;
- $g^{to},b^{to}$: to-side shunt terms;
- $t_m$: transformer tap magnitude;
- $t_r,t_i$: rectangular transformer tap components.

With $\Delta\theta=\theta_i-\theta_j$, the from-side equations in the
`constraint_ohms_yt_*` formulation are:

$$
p_{ij} =
\frac{g+g^{fr}}{t_m^2}v_i^2
 + \frac{-g t_r+b t_i}{t_m^2}v_i v_j\cos(\Delta\theta)
 + \frac{-b t_r-g t_i}{t_m^2}v_i v_j\sin(\Delta\theta)
$$

$$
q_{ij} =
-\frac{b+b^{fr}}{t_m^2}v_i^2
 - \frac{-b t_r-g t_i}{t_m^2}v_i v_j\cos(\Delta\theta)
 + \frac{-g t_r+b t_i}{t_m^2}v_i v_j\sin(\Delta\theta).
$$

For the to-side, with $\Delta\theta'=\theta_j-\theta_i$:

$$
p_{ji} =
(g+g^{to})v_j^2
 + \frac{-g t_r-b t_i}{t_m^2}v_jv_i\cos(\Delta\theta')
 + \frac{-b t_r+g t_i}{t_m^2}v_jv_i\sin(\Delta\theta')
$$

$$
q_{ji} =
-(b+b^{to})v_j^2
 - \frac{-b t_r+g t_i}{t_m^2}v_jv_i\cos(\Delta\theta')
 + \frac{-g t_r-b t_i}{t_m^2}v_jv_i\sin(\Delta\theta').
$$

For a normal line, $t_m=1$, $t_r=1$, and $t_i=0$. Transformer taps and phase
shifts are therefore part of the branch equations, not post-processing.

PowerModels also has `constraint_ohms_y_from` and `constraint_ohms_y_to`, which
use tap magnitude and phase angle directly. The `yt` variant is selected by
the formulation's branch data and stores the transformer ratio in rectangular
form.

## 6. Reference Angle

For every reference bus $r$:

$$
	heta_r = 0.
$$

This removes the rotational degree of freedom in the voltage angles. The
constraint is `constraint_theta_ref`.

## 7. Voltage and Angle Security Limits

The voltage magnitude bounds are applied directly to the ACP voltage variable:

$$
v_i^{\min} \le v_i \le v_i^{\max}.
$$

For every branch, the angle difference is bounded by the input angle limit:

$$
	heta_{ij}^{\min}
\le \theta_i-\theta_j
\le \theta_{ij}^{\max}.
$$

The common symmetric case is:

$$
-\theta^{\max} \le \theta_i-\theta_j \le \theta^{\max}.
$$

The implementation is `constraint_voltage_angle_difference` in the shared
constraint templates.

## 8. Thermal Limits

For a branch rating $S_{ij}^{max}$, PowerModels enforces apparent-power
limits independently at both ends:

$$
p_{ij}^2 + q_{ij}^2 \le (S_{ij}^{max})^2,
$$

$$
p_{ji}^2 + q_{ji}^2 \le (S_{ij}^{max})^2.
$$

If the input specifies a current rating instead, the ACP formulation uses:

$$
p_{ij}^2+q_{ij}^2
\le v_i^2(I_{ij}^{max})^2,
$$

and the analogous to-side equation. The OPF builder calls the apparent-power
thermal constraints by default; current limits are available through the
corresponding constraint template.

## 9. Objective Function

`build_opf` calls `objective_min_fuel_and_flow_cost(pm)`. The objective is the
sum of generator fuel costs and optional branch-flow costs:

$$
\min\quad
\sum_{g\in\mathcal{G}} c_g(p_g)
 + \sum_{(i,j)\in\mathcal{A}} c_{ij}^{flow}(p_{ij},q_{ij}).
$$

The generator cost polynomial is represented by its input coefficients. For a
quadratic cost:

$$
c_g(p_g)=c_{g,2}p_g^2+c_{g,1}p_g+c_{g,0}.
$$

The implementation supports the cost forms represented by the input data,
including polynomial and piecewise-linear costs. If no flow cost is present,
the branch-flow term contributes zero. The objective is not a sum of power
balance residuals.

## 10. Exact `build_opf` Assembly

The implementation in `src/prob/opf.jl` follows this order:

```text
variable_bus_voltage
variable_gen_power
variable_branch_power
variable_dcline_power
objective_min_fuel_and_flow_cost
constraint_model_voltage
constraint_theta_ref for each reference bus
constraint_power_balance for each bus
for each branch:
	constraint_ohms_yt_from
	constraint_ohms_yt_to
	constraint_voltage_angle_difference
	constraint_thermal_limit_from
	constraint_thermal_limit_to
for each DC line:
	constraint_dcline_power_losses
```

This separation is important: the OPF problem builder determines which
network constraints are present, while `ACPPowerModel` determines how the
nonlinear AC equations are represented.

## 11. Formulation Variants in PowerModels.jl

PowerModels contains several formulations of related OPF problems:

| Model | Meaning | Typical property |
| --- | --- | --- |
| `ACPPowerModel` | AC polar formulation | Nonconvex NLP with $v,\theta,p,q$ |
| `ACRPowerModel` | AC rectangular formulation | Nonconvex equations in real and imaginary voltage |
| `ACTPowerModel` | AC lifted/alternative formulation | Different auxiliary variables and relaxations |
| `IVRPowerModel` | AC current-voltage formulation | Nonconvex rectangular voltage/current equations |
| `DCPPowerModel` | DC approximation | Linearized active-power model |
| `DCMPowerModel` | Transformer-aware DC approximation | Linearized active-power model with transformer terms |
| `BFAPowerModel` | Branch-flow approximation | Linearized active-power branch equations |
| `NFAPowerModel` | Network-flow approximation | Linearized active-power network equations |
| `SOCWRPowerModel` | SOC relaxation | Convex relaxation of selected AC relationships |
| `SDPWRMPowerModel` | SDP relaxation | Semidefinite relaxation |

`solve_ac_opf` specifically selects `ACPPowerModel`. The existence of
relaxations in the repository does not mean the normal ACOPF call uses them.

## 12. Available `o_grid` Formulations

These are the formulations exposed by the dedicated `o_grid.acopf` package.
They are not the legacy ACPF modes in `o_grid.acpf.optimization`. The public
strict ACOPF entry point is:

```python
from o_grid.acopf import ACOptimalPowerFlow

run = ACOptimalPowerFlow(
	formulation="ACPPowerModel",
	objective_function="voltage_deviation",
).run("case.pwf")
```

`formulation` accepts the PowerModels model names registered by
`o_grid.acopf.formulations`. The currently executable formulations are
`ACPPowerModel`, `ACRPowerModel`, `ACTPowerModel`, `IVRPowerModel`,
`DCPPowerModel`, `DCMPPowerModel`, `BFAPowerModel`, `NFAPowerModel`,
`SOCWRPowerModel`, `SOCBFPowerModel`, `SDPWRMPowerModel`, and
`SparseSDPWRMPowerModel`. The SOC and SDP formulations are solved through
the Julia Clarabel bridge. The package ships a Julia project that resolves
Clarabel `v0.11.1` directly from GitHub and instantiates it on first use. An
alternate Julia project can still be supplied with the `clarabel_project`
constructor argument or `O_GRID_CLARABEL_PROJECT`. Julia 1.10 or newer and
network access are required for the initial dependency installation.

`SDPWRMPowerModel` is the dense global PSD prototype and is deliberately
limited to small cases. `SparseSDPWRMPowerModel` uses the exact SOC
representation of each network-edge 2-by-2 Hermitian PSD block, so it keeps
network sparsity and can run on larger cases. It is not a full chordal SDP;
global clique decomposition and overlap consistency constraints require a
backend with sparse multi-PSD support.

The public ACOPF solver uses the voltage-deviation formulation:

```python
from o_grid.acopf import ACOptimalPowerFlow

run = ACOptimalPowerFlow(objective_function="voltage_deviation").run("case.pwf")
```

The available formulation choices in the dedicated ACOPF model builder are:

| Method | Balance equations | Security limits | Objective/use |
| --- | --- | --- | --- |
| `voltage_deviation` | Exact AC balance | Hard voltage, angle, and thermal limits | Only dedicated `ACOptimalPowerFlow` formulation |

The legacy `o_grid.acpf.optimization.OptimizationACPowerFlow` remains a
separate solver and preserves its own objective modes. Those modes are not
part of the dedicated ACOPF API.

The voltage-deviation formulation is selected through the ACOPF objective flag:

```python
run = ACOptimalPowerFlow(
	objective_function="voltage_deviation",
    tolerance=1.0e-3,
    max_iterations=100,
).run("case.pwf")
```

Its principal objective is:

$$
\min \sum_{i\in\mathcal{B}}(v_i-1)^2
$$

with small dispatch regularization terms that keep active and reactive
generation near the input operating point. Generator dispatch remains bounded
by the available case limits or conservative fallback limits when the input
does not provide explicit limits.

The conic formulations use a sparse W-space relaxation and currently export
network balance, voltage bounds, generator bounds, and selected SVC/shunt
injections. Discrete controller behavior, variable transformer controls,
full generator metadata, and complete security constraints are not yet
represented. Reported angles are reconstructed from the solved W variables.

The linear formulations solve their declared linearized equations, but their
results are not necessarily AC-feasible. In particular, DCP-family models do
not represent reactive transformer physics; a small linear residual can still
produce a large exact AC branch-flow violation. Comparison tools should report
these as linearized solutions with failed AC security validation, rather than
as numerical solver failures.

## 13. Solver and Termination Semantics

PowerModels builds a JuMP model and passes it to the optimizer supplied by the
caller, commonly Ipopt for `ACPPowerModel`:

```julia
result = solve_ac_opf(data, Ipopt.Optimizer)
```

Ipopt's `LOCALLY_SOLVED` or `OPTIMAL` status means that the nonlinear optimizer
met its own termination criteria for the model it received. It does not mean
that a different post-processing model is feasible. A correct implementation
must inspect:

- primal constraint residuals;
- variable-bound violations;
- thermal and angle-limit violations;
- generator-bound violations;
- the solver termination status.

PowerModels keeps these as model constraints and lets JuMP/Ipopt report the
solution. It does not convert a failed nonlinear solve into a converged result
by relaxing residuals after the solve.

## 14. Comparison with `o_grid`

The intended PowerModels-equivalent implementation in `o_grid` should have:

1. Generator-level $p_g$ and $q_g$ variables with data-derived bounds.
2. Bus-level exact active and reactive KCL equalities.
3. Explicit branch-end $p,q$ variables tied to voltage by the same Ohm
   equations, including tap and phase-shift conventions.
4. Direct voltage, angle, and thermal constraints.
5. A generation-cost objective, rather than a residual objective, for ACOPF.
6. A final validation pass using the same state and equations used in the
   optimization model.

The dedicated `o_grid.acopf` module is a Pyomo implementation inspired by
this structure. Its public
`ACOptimalPowerFlow(objective_function="voltage_deviation")`
class is the only dedicated ACOPF entry point. The legacy
`o_grid.acpf.optimization.OptimizationACPowerFlow` is a separate solver and
must not be used to describe the dedicated ACOPF formulation.

## 15. Practical Interpretation

For the Brazilian case, increasing `max_iter` or using a relaxed residual
objective can produce an Ipopt point more quickly, but it does not establish a
secure ACOPF solution. To match the PowerModels approach, the strict model
must converge with:

$$
\max_i |\Delta P_i| \le \varepsilon_P,
\qquad
\max_i |\Delta Q_i| \le \varepsilon_Q,
$$

and all voltage, generator, angle, and branch limits satisfied. If this does
not happen, the correct status is infeasible or non-converged, not optimal
ACOPF.
