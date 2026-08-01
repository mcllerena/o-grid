# Newton-Raphson AC Power Flow in o-grid

This document describes the sparse, full **Newton-Raphson** (NR) solver that
`o-grid` uses to solve the ANAREDE power-flow cases (`.pwf`) of the Brazilian
interconnected system. It covers the mathematical theory, the numerical
techniques used to force convergence on real Brazilian cases, and the role of
every control/device model in `src/o_grid/acpf/models/`.

The implementation lives in
[`src/o_grid/acpf/newton_raphson.py`](src/o_grid/acpf/newton_raphson.py); the
case construction, orchestration, and control pass loop are in
[`src/o_grid/acpf/models/`](src/o_grid/acpf/models/) and
[`src/o_grid/acpf/solver.py`](src/o_grid/acpf/solver.py). All quantities are
per-unit on the case base `BASE` (MVA) unless noted otherwise.

---

## 1. The power-flow problem

A power system is described by the nodal admittance equation

$$
\vec{I} = \mathbf{Y} \, \vec{V},
$$

where $\mathbf{Y}$ is the complex bus admittance matrix and the complex power
injected at bus $i$ is

$$
S_i = P_i + jQ_i = V_i \,\overline{I}_i = V_i \sum_{k} \overline{Y_{ik}}\, \overline{V_k}.
$$

With $\vec{V} = \mathbf{Y}^{-1}\vec{I}$ unknown, each bus contributes **two**
unknowns ($V_i$, $\theta_i$) and at most **two** equations, so each bus
specifies two quantities. Following ANAREDE practice, `o-grid` classifies buses
as:

| Type | Specified | Unknowns | Set in `PowerFlowCase` |
| --- | --- | --- | --- |
| Slack / Reference (`SLACK`, `REF`) | $V$, $\theta$ | $P$, $Q$ | `slack_indices` |
| Generator (`PV`) | $P$, $V$ | $\theta$, $Q$ | `pv_indices` |
| Load (`PQ`) | $P$, $Q$ | $V$, $\theta$ | `pq_indices` |

In per-unit form the specified injection at bus $i$ is

$$
S_i^{sp} = \frac{(P_{g,i} - P_{l,i}) + j\,(Q_{g,i} - Q_{l,i})}{S_{base}},
$$

where $P_g, Q_g$ are the generation and $P_l, Q_l$ the load attached to the bus.
`PowerFlowCase.specified_power` builds exactly this vector from the parsed
`DBAR` records, augmented with `DCAI` individualized loads, SVC and LCC
injections, and the shunt compensation.

The power-flow problem is to find $\vec{V}$ such that the **power mismatches**
vanish:

$$
\Delta P_i = P_i^{sp} - P_i^{calc}(V,\theta) = 0,
\qquad
\Delta Q_i = Q_i^{sp} - Q_i^{calc}(V,\theta) = 0.
$$

`calculate_power` (`utils/network.py`) computes the calculated injections as

$$
\vec{S}^{calc} = \vec{V} \odot \overline{\mathbf{Y}\,\vec{V}}.
$$

## 2. The full Newton-Raphson method

### 2.1 Polar-coordinate formulation

The solver works in polar coordinates $V_i\,e^{j\theta_i}$. The state vector
groups every angle of the $PV\cup PQ$ buses and every magnitude of the $PQ$
buses:

$$
\vec{x} =
\begin{bmatrix}
\theta_{PV \cup PQ} \\[2pt]
|V|_{PQ}
\end{bmatrix}.
$$

The mismatch vector is

$$
\vec{F}(\vec{x}) =
\begin{bmatrix}
\Delta P_{PV \cup PQ} \\[2pt]
\Delta Q_{PQ}
\end{bmatrix}.
$$

### 2.2 The Newton iteration

Starting from an initial guess $\vec{x}^{(0)}$, each iteration solves the
linear system

$$
\mathbf{J}\,\Delta\vec{x} = -\vec{F}(\vec{x}),
$$

updates $\vec{x}^{(k+1)} = \vec{x}^{(k)} + \Delta\vec{x}$, and repeats until
$\|\vec{F}\|_\infty \le \varepsilon$. The solver uses the **exact** Jacobian of
the polar power equations, assembled in `_build_jacobian` from complex matrix
algebra. Note that `_build_jacobian` returns the Jacobian of the *calculated*
injections $\partial\vec{S}/\partial\vec{x}$ (no sign flip) and the code solves
$\partial\vec{S}/\partial\vec{x}\,\Delta\vec{x} = \vec{S}^{sp}-\vec{S}^{calc}$;
multiplying both sides by $-1$ gives the textbook form $\mathbf{J}\Delta\vec{x}=-\vec{F}$
with $\mathbf{J}=-\partial\vec{S}/\partial\vec{x}$, so the two formulations are
identical.

### 2.3 The Jacobian and its four blocks

The complex power sensitivity is built from the current $\vec{I} = \mathbf{Y}\vec{V}$:

$$
\frac{\partial \vec{S}}{\partial |V|}
= \operatorname{diag}(\vec{V})\, \left(\mathbf{Y}\,
\operatorname{diag}\!\left(\vec{V}/|\vec{V}|\right)\right)^*
+ \left(\operatorname{diag}(\vec{I})\right)^*
\,\operatorname{diag}\!\left(\vec{V}/|\vec{V}|\right),
$$

$$
\frac{\partial \vec{S}}{\partial \theta}
= j\,\operatorname{diag}(\vec{V})
\, \left(\operatorname{diag}(\vec{I}) - \mathbf{Y}\,\operatorname{diag}(\vec{V})\right)^* .
$$

The real (active) and imaginary (reactive) parts are then projected onto the
bus-type partitions to form the four classic blocks:

$$
\mathbf{J} =
\begin{bmatrix}
\dfrac{\partial \Delta P}{\partial \theta} & \dfrac{\partial \Delta P}{\partial |V|} \\[8pt]
\dfrac{\partial \Delta Q}{\partial \theta} & \dfrac{\partial \Delta Q}{\partial |V|}
\end{bmatrix}
=
\begin{bmatrix}
\operatorname{Re}\!\left(\frac{\partial S}{\partial\theta}\right)_{PV\cup PQ,\,PV\cup PQ}
& \operatorname{Re}\!\left(\frac{\partial S}{\partial |V|}\right)_{PV\cup PQ,\,PQ} \\[8pt]
\operatorname{Im}\!\left(\frac{\partial S}{\partial\theta}\right)_{PQ,\,PV\cup PQ}
& \operatorname{Im}\!\left(\frac{\partial S}{\partial |V|}\right)_{PQ,\,PQ}
\end{bmatrix}.
$$

Because $S = V\,\overline{YV}$, these matrix expressions are exact and require
no per-entry derivatives, only sparse matrix products. The four blocks are
stacked with `scipy.sparse` `hstack`/`vstack` into a single `csc_matrix`
Jacobian.

### 2.4 Sparse linear algebra

The Jacobian is solved with `scipy.sparse.linalg.spsolve`, which performs a
sparse **LU factorization** and forward/back substitution:

$$
\Delta\vec{x} = \mathbf{J}^{-1}\vec{F}
\quad\Longleftrightarrow\quad
\mathbf{L}\mathbf{U}\,\Delta\vec{x} = \vec{F}.
$$

### 2.5 Convergence criterion

The residual is the largest absolute mismatch:

$$
R = \max\left( \max_{i\in PV\cup PQ} |\Delta P_i|,\;
\max_{i \in PQ} |\Delta Q_i| \right).
$$

The solve **converges** when $R \le \varepsilon$, with

$$
\varepsilon = \min\!\left(\varepsilon_P,\, \varepsilon_Q\right),
\qquad
\varepsilon_P = \frac{\mathrm{TEPA}}{S_{base}},
\qquad
\varepsilon_Q = \frac{\mathrm{TEPR}}{S_{base}},
$$

i.e. the ANAREDE active/reactive tolerance constants (MW / MVAr) converted to
per-unit on the case base. Defaults are `TEPA = TEPR = 0.1` MW/MVAr, which on a
100 MVA base give $\varepsilon = 10^{-3}$ p.u. (`build_power_flow_settings`).

## 3. Making Brazilian PWF cases converge

Real `.pwf` cases are large (the `CASO_FINAL_EQV2020` case has 247 buses and
605 `DLIN` records), contain switches, jumper buses, isolated islands, HVDC
links, and many closed-loop voltage controllers. The following strategies, all
mirroring the behavior of the ANAREDE/C++ reference solver, are applied.

### 3.1 Case construction from ANAREDE records

`build_power_flow_case` turns the parsed infrasys system into the numerical
`PowerFlowCase`:

* `DBAR` → `BusData` (type, $P_g$, $Q_g$, $P_l$, $Q_l$, voltage limits, base
  voltage, voltage group, generator $Q$ limits).
* `DLIN` and derived `DLIN_TAP` / `DLIN_PHASE_SHIFT` / `DLIN_TRANSFORMER` /
  `DLIN_SWITCH` → `BranchData`. Impedances are read in **per-cent** and divided
  by 100 ($z = \frac{R}{100} + j\frac{X}{100}$ p.u.); phase shifts are converted
  from degrees to radians and **negated** to match the ANAREDE sign convention.
* `DCAI` individualized loads, `DSHL` line shunts, `DBSH`/`DBSH_BANK` capacitor
  banks, `DCER` SVCs, and `DCNV`/`DCLI`/`DELO`/`DCBA`/`DCCV` HVDC records are
  applied on top of the bus records (see §4).

### 3.2 Settings from PWF constants and options

The solver is tuned entirely by the case itself (`build_power_flow_settings`):

| PWF constant | Meaning | Used as |
| --- | --- | --- |
| `TEPA`, `TEPR` | Active / reactive convergence tolerance | $\varepsilon_P,\ \varepsilon_Q$ (÷ base MVA) |
| `ACIT` | Max Newton iterations | `max_iterations` |
| `TLVC` | Voltage control tolerance (0.5 % default) | ×0.01 → p.u. band for `VLIM` |
| `VDVN`, `VDVM` | Divergence voltage bounds (40 %, 200 %) | reject $|V| < 0.4$ or $> 2.0$ |
| `ASTP` | Max angle step (0.05 rad) | `max(5°, |ASTP|)` |
| `VSTP` | Max voltage step (5 % default) | ×0.01 → p.u. clamp |
| `ZMIN` | Low-impedance threshold | `max(2.000001e-4, ZMIN×0.01)` |
| `BASE` | System base power | per-unit normalization (100 MVA default) |

Activated `DOPC` options (e.g. `QLIM`, `VLIM`) enable the corresponding
irreversible bus-type conversions of §4.7.

### 3.3 Network reduction: switches and jumper buses

Brazilian buses are heavily switch-connected (`DLIN_SWITCH`) and contain many
zero/low-impedance "jumper" branches. Solving on the full topology makes the
Jacobian ill-conditioned. `reduce_closed_switches`
(`models/network_reduction.py`) therefore **contracts** every electrically
equivalent bus before the solve using a union–find over the branch graph.

A branch is contracted when any of the following holds:

* it is a closed switch (`is_switch`), or
* $|z| = \sqrt{R^2+X^2} \le 2.000001\times10^{-4}$ p.u. (the `ZMIN` floor), or
* $2\times10^{-4} < |z| \le 1.05\times10^{-3}$ p.u. **and** the endpoints share
  a voltage group (or equal base voltage) **and** the branch is heavily loaded
  (apparent flow $> 1.25\times$ rating).

Branches with taps or phase shifts are never contracted. Each contracted group
keeps a single **representative bus** chosen by `(kind priority, external
degree)`, preferring `SLACK`/`REF` over `PV` over `PQ`, and sums the group's
generation, load, and shunt susceptance into it. Internal branches are dropped;
taps/phase shifts of surviving branches are preserved. The mapping back to the
original buses is kept in `ReducedPowerFlowCase.original_to_reduced`, so the
solved voltages are expanded with `expand_voltage` and the solved control state
is copied back with `sync_control_state` after the solve.

Auxiliary "U"-group buses (voltage-group `U`, used by ANAREDE for tapped
coupling buses) are initialized before reduction so that a branch of impedance
$|z| \le 1.05\times10^{-3}$ linking a normal bus and a `U` bus seeds the `U`
bus voltage from the tap:

$$
V_U = \frac{V_{other}}{a}, \qquad \theta_U = \theta_{other} - \phi.
$$

### 3.4 Reference buses per island

After reduction the case may contain islands without any reference bus.
`assign_island_reference_buses` (`utils/network.py`) runs a connected-components
search on $\mathbf{Y}$ and, for each island lacking a `REF`/`SLACK` bus, promotes
the `PV` bus with the largest active generation to `SLACK`. This keeps every
island solvable with a well-posed angle reference.

### 3.5 Warm start

Newton–Raphson needs a decent starting point. Before the main loop, the solver
tries **two** seeds and keeps the better one:

1. the **parsed** initial voltage/angles read from the PWF (`DBAR` fields), and
2. a **flat** seed $|V| = |V^{parsed}|$, $\theta = 0$.

Each seed is pre-conditioned with up to 24 iterations of an **angle-only**
reduced solve ($\partial \Delta P/\partial\theta$ block) that drives the active
mismatch below 0.1 p.u. using damped backtracking. The seed with the smaller
active residual on $PV\cup PQ$ is chosen. This is the same "phase angle
initialization" strategy ANAREDE applies to cases that start from base-case
voltages.

### 3.6 Line search and step control

A full Newton step can overshoot on hard cases. `_line_search` applies a
backtracking line search: starting from $\mu=1$, it halves the step up to 16
times until the resulting mismatch is no larger than the current residual:

$$
\vec{x}^{(k+1)} = \vec{x}^{(k)} + \mu\,\Delta\vec{x},
\qquad
\|\vec{F}(\vec{x}^{(k+1)})\|_\infty \le \|\vec{F}(\vec{x}^{(k)})\|_\infty.
$$

Trial magnitudes are additionally **clipped** to the bus operational band

$$
\max(0.5,\ 0.8\,V_{min,i}) \;\le\; |V_i| \;\le\; \max(1.5,\ 1.5\,V_{max,i}),
$$

so the iteration never accepts physically meaningless voltages.

### 3.7 Divergence detection

The solver gives up cleanly (returning `diverged=True`) instead of polluting
the solution when:

* the LU factorization signals a rank-deficient matrix
  (`MatrixRankWarning`, `FloatingPointError`, `RuntimeError`, `ValueError`),
* the Newton step contains non-finite entries, or
* any bus magnitude leaves $[0.4,\, 2.0]$ p.u. (the `VDVN`/`VDVM` bounds).

When the iteration budget `ACIT` is exhausted without converging, the run is
marked *did not converge* (not diverged), which triggers the Fast-Decoupled
solver's Newton fallback path (§5).

## 4. Control and device models in `acpf/models/`

Every model file contributes either network data (stamped into $\mathbf{Y}$ and
$\vec{S}^{sp}$) or a control update (a post-solve adjustment re-linearized in
the outer control loop). For each device below, the model is described together
with the equation it contributes.

### 4.1 `case.py` — `PowerFlowCase`, `BusData`, `BranchData`

The central numerical data structure. `BusData` carries the per-unit specified
injections and bus limits; `BranchData` carries the series impedance, charging,
tap, phase shift, and LTC/PST control data. The bus-type index sets
(`slack_indices`, `pv_indices`, `pq_indices`) and the specified-power vector
(§1) are properties of `PowerFlowCase`. All solvers consume only this model.

### 4.2 `utils/network.py` — `build_ybus`

The nodal admittance matrix is assembled branch by branch. For a branch
$f\!-\!t$ with series impedance $z = r + jx$, admittance $y = 1/z$, half-line
charging $jb/2$, tap $a$ and phase shift $\phi$ (complex tap
$t = a\,e^{j\phi}$), the contribution is

$$
\mathbf{Y}_{ff} \mathrel{+}= \frac{y + j\frac{b}{2}}{|t|^2},
\qquad
\mathbf{Y}_{tt} \mathrel{+}= y + j\frac{b}{2},
\qquad
\mathbf{Y}_{ft} \mathrel{-}= \frac{y}{\bar t},
\qquad
\mathbf{Y}_{tf} \mathrel{-}= \frac{y}{t}.
$$

Bus shunts are added to the diagonal as $\mathbf{Y}_{ii} \mathrel{+}= j b^{sh}_i$.
`calculate_power` then evaluates $\vec{S} = \vec{V}\odot\overline{\mathbf{Y}\vec{V}}$
— the one function every solver, control trial, and the Jacobian assembly
depends on.

### 4.3 `settings.py` — `PowerFlowSettings`

Carries the tolerances, step limits, divergence bounds, and `DOPC` option set
derived from PWF constants (see the table in §3.2). `PowerFlowSettings.enabled`
is used by the QLIM/VLIM logic.

### 4.4 `svc.py` — `SVCData` and `adjust_svc_reactive_power`

Static VAR compensators (PWF `DCER`). The model stores the connected and
controlled bus, the control mode, the **droop slope** $X_s$ (per-unit, from the
PWF slope % ×0.01), the reactive range, and the reference voltage. Only SVCs on
**PQ** buses participate in the iterative control.

The droop control law implemented is the classic slope model

$$
Q = \frac{V_{ref} - V_{ctrl}}{X_s}\, V_{bus}\, S_{base}
\qquad\text{(current-type, mode ends in "I")},
$$

$$
Q = \frac{V_{ref} - V_{ctrl}}{X_s}\, S_{base}
\qquad\text{(admittance-type)},
$$

clipped to the voltage-scaled reactive limits

$$
Q_{min}\, V_{ctrl}^2 \;\le\; Q \;\le\; Q_{max}\, V_{ctrl}^2 .
$$

The change $\Delta Q$ is added to `BusData.reactive_generation` of the SVC bus,
i.e. $\vec{S}^{sp}$ is updated before the re-solve.

### 4.5 `shunt.py` — `ShuntControlData` and `adjust_switched_shunts`

Switched capacitor/reactor banks (PWF `DBSH` + `DBSH_BANK`). The initial bank
susceptance is stamped into the bus as $jQ_{init}/S_{base}$; the control model
keeps the achievable $[Q_{min}, Q_{max}]$ range and the dead-band voltage band.

The control is a **bang-bang** (discrete) voltage controller:

$$
V_{ctrl} > V_{max} + 10^{-3} \;\Rightarrow\; Q = \min(0,\ Q_{min}),
$$

$$
V_{ctrl} < V_{min} - 10^{-3} \;\Rightarrow\; Q = \max(0,\ Q_{max}).
$$

The change $\Delta Q$ is applied to the bus shunt susceptance
($b^{sh} \mathrel{+}= \Delta Q/S_{base}$), which modifies the diagonal of
$\mathbf{Y}$.

### 4.6 `ltc.py` — `adjust_ltc_taps`

Load tap changers (PWF `DLIN_TAP`). The tap $a$ enters the $\mathbf{Y}$ matrix
through the complex tap $t = a\,e^{j\phi}$ of §4.2. The control drives the
controlled-bus voltage to its target with a **bounded proportional step** (max
1 % tap change per pass):

$$
\Delta a = \operatorname{clip}\!\left(\pm\,0.5\,(V_{target} - V_{ctrl}),\; -0.01,\; 0.01\right),
$$

$$
a^{(new)} = \operatorname{clip}\!\left(a + \Delta a,\; a_{min},\; a_{max}\right),
$$

where the sign depends on whether the controlled bus is the $from$ ($+$) or $to$
($-$) side. Branches without a control bus or without a valid tap range are
skipped. After a tap change the solver rebuilds $\mathbf{Y}$ and re-solves.

### 4.7 `pst.py` — `apply_pst_to_branch`

Phase-shifting transformers (PWF `DLIN_PHASE_SHIFT`). The fixed PWF phase is
applied as $\phi = -\mathrm{radians}(\phi_{PWF})$, and any explicit `DLIN`
impedance overrides the branch $r/x$. The phase shift enters the network
through $t = a\,e^{j\phi}$ in $\mathbf{Y}$, actively steering the branch power
flow.

### 4.8 `csc.py` — `apply_csc_to_branches` and `is_active_csc`

Controllable series compensators (PWF `DCSC`) are applied **statically** when
the case is built: the CSC reactance is added in series with an existing branch,
or a standalone purely reactive branch $z = j\,x_{csc}$ is created. `is_active_csc`
filters out compensators that are out of service, in bypass, or inoperative.
A CSC therefore only changes $\mathbf{Y}$ (via the series $y = 1/(r+j(x+x_{csc}))$);
it does not take part in the control-pass loop.

### 4.9 `lcc.py` — `LCCData`, `build_lcc_data`, `update_lcc_from_dc_solution`

Line-commutated converter HVDC links (PWF `DCNV`/`DCLI`/`DELO`/`DCBA`/`DCCV`,
i.e. Itaipu-style bipoles). Pairs of converters (one rectifier "R", one
inverter "I") are linked through `DCLI` records; exactly one converter must be
the `DCCV` slack (`Folga`). The model is a **constant-current** DC representation:

$$
I_{dc} = \frac{P_{dc}}{V_{dc}^{ref}}, \qquad
P_{loss} = I_{dc}^{2}\, R_{dc}.
$$

Depending on which side is the slack converter, the terminal powers and DC
voltages are:

$$
\text{rectifier slack:}\quad
P_{rect} = P_{dc} + P_{loss}, \quad
V_{dc}^{rect} = V_{dc}^{inv} + I_{dc}R_{dc}, \quad
P_{inv} = P_{dc},
$$

$$
\text{inverter slack:}\quad
P_{rect} = P_{dc}, \quad
V_{dc}^{inv} = \max(0,\ V_{dc}^{rect} - I_{dc}R_{dc}), \quad
P_{inv} = \max(0,\ P_{dc} - P_{loss}).
$$

The AC-side reactive consumption follows the converter equations

$$
Q_{rect} = P_{rect}\,\tan\!\left(\alpha + \tfrac{\mu}{2}\right),
\qquad
Q_{inv} = P_{inv}\,\tan\!\left(\gamma + \tfrac{\mu}{2}\right),
$$

where $\alpha$ is the firing angle and $\mu$ the **overlap angle**, obtained
from the commutation equation

$$
\cos(\mu + \alpha) = \cos\alpha - \frac{\sqrt{2}\, X_c\, I_{dc}}{V_t},
\qquad
V_t = a\, V_{bridge}\, V_{ac}^{pu},
$$

with $X_c$ the commutation reactance (per-cent × 0.01 × $V_{bridge}^2/S_{nom}$).
The converter transformer taps target the ideal six-pulse voltage law

$$
V_{dc} = 0.995 \cdot \frac{3\sqrt{2}}{\pi}\, n\, a\, V_{bridge}\, V_{ac}^{pu}
\cos\!\left(\alpha + \tfrac{\mu}{2}\right),
$$

and are clamped to their tap ranges. All injection, voltage, and tap updates are
**damped** with factor $\lambda = 0.3$:
$x^{(new)} = (1-\lambda)\,x + \lambda\,x^{target}$.

In the case, the rectifier draws $P_{rect} + jQ_{rect}$ (load) and the inverter
injects $P_{inv}$ while drawing $jQ_{inv}$. **Because the DC link couples active
and reactive strongly, any case containing LCCs is solved with the full
Newton-Raphson method** (§5); the fast-decoupled solver delegates to it.

### 4.10 `controls.py` — QLIM and VLIM

These mirror the ANAREDE power-flow option flags and are irreversible
topology/type changes applied **once** at the start of the control loop:

* **`QLIM`** — generator reactive limits. For each `PV` bus with limits, the
  reactive generation actually required is estimated as

$$
Q_{req} = \operatorname{Im}(S^{calc})\, S_{base} + Q_{load} - Q_{svc}.
$$

  If $Q_{req} > Q_{max} + 0.1$ (or $< Q_{min} - 0.1$), the bus is converted
  `PV → PQ` with $Q_g$ fixed at the violated limit, removing $V$ from its
  specified set.

* **`VLIM`** — voltage limits. For each `PQ` bus, if $|V_i|$ leaves
  $[V_{min}, V_{max}]$ by more than the `TLVC` band, the bus is converted
  `PQ → PV` with $|V_i|$ fixed at the violated limit.

Both conversions change the index sets `pv_indices`/`pq_indices` used to build
the Jacobian, so they must be applied before the re-solve.

### 4.11 `network_reduction.py` — `ReducedPowerFlowCase`

Not a physical device but a preconditioner (see §3.3). It keeps the
bus mapping, expands the solved voltages back to the original topology, and
copies the solved taps, SVC/shunt injections, and LCC terminal powers back onto
the original (uncontracted) case for reporting.

### 4.12 `solution.py` and `results.py` — solution and reporting state

`NumericalSolution` holds the complex voltage vector, the convergence flags, and
the per-iteration trace. `results.py` defines the typed `ACPowerFlowResult` and
the per-iteration rows (`max_dp`, `max_dq`, `max_residual`, `max_step`) that the
live reporter prints. `result_builder.py` later maps the solved buses/branches
back to the infrasys result components (`ACBusResults`, `ACLineResults`,
`LTCTransformerResults`, ...) and computes reporting quantities such as
voltage violations, branch loading, and power losses.

## 5. Orchestration in `solver.py`

`NewtonRaphsonPowerFlow.run` implements the full outer algorithm:

```text
1. build PowerFlowCase + PowerFlowSettings from the parsed system
2. reduce_closed_switches(case)                 # contract switches/jumpers
3. ybus = build_ybus(case); assign_island_reference_buses(case, ybus)
4. solve_newton_raphson(case, ybus, eps, ACIT)  # base solve (+ warm start)
5. control loop (up to 12 passes), in order:
     a. bus limits (QLIM/VLIM)            — pass 0 only
     b. adjust_svc_reactive_power
     c. adjust_switched_shunts
     d. adjust_ltc_taps
     e. update_lcc_from_dc_solution
   for each accepted change: rebuild ybus, re-solve from the control voltage;
   reject and restore the previous solution if the re-solve fails
6. sync_control_state back to the full case
7. expand_voltage to the original topology
8. build results; attach solved values to the infrasys system
```

The control loop is the key to converging the Brazilian cases: every device that
violates its limit is adjusted, the network is re-linearized with a fresh
$\mathbf{Y}$, and the solve is repeated until either no control changes or the
changes no longer converge. The current best converged solution is always
restored when a control trial fails.

## 6. From solution to infrasys results

After convergence, `calculate_bus_results` and `calculate_branch_results`
(`utils/network.py`) evaluate the final injections

$$
S_i = V_i\,\overline{(\mathbf{Y}\vec{V})_i}\, S_{base},
$$

and, per branch, the terminal flows

$$
I_{ft} = \frac{y + j\frac{b}{2}}{|t|^2}\, V_f - \frac{y}{\bar t}\, V_t,
\qquad
S_{ft} = V_f\,\overline{I_{ft}}\, S_{base},
$$

the loading

$$
\mathrm{loading}\% = 100 \cdot \frac{\max(|S_{ft}|,\,|S_{tf}|)}{\text{rating}},
$$

and the losses $S_{loss} = S_{ft} + S_{tf}$. `apply_power_flow_result` writes
the solved bus voltages, angles, and injections back to the infrasys `ACBus`
objects, and `build_component_results` produces the typed result components and
statistics table consumed by `system.set_power_flow_results` and the Excel
exporter.

## References

* Tinney, W. F., Hart, C. E., "Power Flow Solution by Newton's Method," *IEEE
  Trans. Power App. Syst.*, 1967.
* Stott, B., "Review of Load-Flow Calculation Methods," *Proc. IEEE*, 1974.
* ANAREDE power-flow manual (execution codes `DBAR`, `DLIN`, `DGER`, `DCER`,
  `DCSC`, `DCNV`, `DCLI`, `DELO`, `DCCV`, `DBSH`, and program constants
  `TEPA`, `TEPR`, `ACIT`, `VDVN`, `VDVM`, `ZMIN`).
