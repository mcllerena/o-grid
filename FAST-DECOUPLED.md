# Fast-Decoupled AC Power Flow in o-grid

This document describes the **fast-decoupled** (FD) solver that `o-grid` uses to
solve ANAREDE power-flow cases (`.pwf`) of the Brazilian interconnected system.
It covers the decoupling theory, the constant-matrix iteration used by the
implementation, the numerical measures taken to converge real Brazilian cases,
and the role of every model in `src/o_grid/acpf/models/`.

The implementation lives in
[`src/o_grid/acpf/fast_decoupled.py`](src/o_grid/acpf/fast_decoupled.py); the
case construction, control loop, and Newton-Raphson fallback are shared with the
Newton-Raphson solver and live in [`src/o_grid/acpf/models/`](src/o_grid/acpf/models/)
and [`src/o_grid/acpf/solver.py`](src/o_grid/acpf/solver.py). This document
assumes familiarity with the power-flow formulation; a full treatment of the
problem statement, the case construction, and the network reduction is given in
[NEWTON-RAPHSON.md](NEWTON-RAPHSON.md) (§1, §3).

---

## 1. The power-flow problem (recap)

Bus injections in per-unit on the case base $S_{base}$:

$$
S_i^{sp} = \frac{(P_{g,i} - P_{l,i}) + j\,(Q_{g,i} - Q_{l,i})}{S_{base}},
\qquad
S_i^{calc} = V_i \sum_k \overline{Y_{ik}}\, \overline{V_k}.
$$

The unknowns are $\theta_{PV\cup PQ}$ and $|V|_{PQ}$; the mismatches to drive to
zero are

$$
\Delta P_i = P_i^{sp} - P_i^{calc}, \qquad
\Delta Q_i = Q_i^{sp} - Q_i^{calc}.
$$

For a full treatment of bus types, the admittance matrix $\mathbf{Y}$, and the
per-unit conventions, see [NEWTON-RAPHSON.md](NEWTON-RAPHSON.md).

## 2. Decoupling theory

### 2.1 Why active and reactive decouple

In the full Newton-Raphson Jacobian (see NEWTON-RAPHSON.md §2.3),

$$
\begin{bmatrix}
\Delta P \\ \Delta Q
\end{bmatrix}
=
\begin{bmatrix}
\mathbf{H} & \mathbf{N} \\ \mathbf{M} & \mathbf{L}
\end{bmatrix}
\begin{bmatrix}
\Delta \theta \\ \Delta |V|/|V|
\end{bmatrix},
$$

the off-diagonal blocks $\mathbf{N} = \partial \Delta P/\partial |V|$ and
$\mathbf{M} = \partial \Delta Q/\partial \theta$ are, for the transmission
networks of the Brazilian system, **numerically small** because

* series reactances dominate resistances ($X \gg R$),
* branch angle differences are small ($\cos\theta_{ik} \approx 1$, and the
  reactive flow depends mostly on voltage magnitudes while the active flow
  depends mostly on angles).

This is the classical Stott–Alsac observation: **$P$ is coupled mainly to
$\theta$, and $Q$ is coupled mainly to $|V|$.** Dropping $\mathbf{N}$ and
$\mathbf{M}$ splits one coupled problem into two smaller, independent systems:

$$
\frac{\Delta P}{|V|} = \mathbf{B'}\, \Delta\theta,
\qquad
\frac{\Delta Q}{|V|} = \mathbf{B''}\, \Delta |V|.
$$

### 2.2 The constant matrices $\mathbf{B'}$ and $\mathbf{B''}$

In the classical formulation $\mathbf{B'}$ and $\mathbf{B''}$ are the
**imaginary parts of the bus admittance matrix** (susceptances), with the
shunt terms removed from $\mathbf{B''}$. `o-grid` builds them directly from
$\mathbf{Y}$ (`_build_decoupled_matrices`):

$$
\mathbf{B'} = \mathbf{B''} = -\operatorname{Im}(\mathbf{Y}).
$$

Both matrices are **constant**: they are assembled once before the iteration
and never rebuilt, unlike the Newton-Raphson Jacobian which changes every
iteration. This is the defining property of the fast-decoupled method — one
sparse factorization per matrix pays for many iterations.

### 2.3 The decoupled iteration in o-grid

At each iteration the implementation:

1. Evaluates the calculated injections and the mismatches
   $\Delta P$ (on $PV\cup PQ$) and $\Delta Q$ (on $PQ$).
2. Solves the **active** system with the fixed factorization
   $\mathbf{L}_P\mathbf{U}_P = \mathbf{B'}_{PV\cup PQ}$:

$$
\Delta\theta = \mathbf{B'}_{PV\cup PQ}^{-1}\, \Delta P_{PV\cup PQ},
$$

    and **clips** the step to $\pm$`max_angle_step` (default $\pm 5^{\circ}$):

$$
\Delta\theta \leftarrow \operatorname{clip}(\Delta\theta,\; -5^{\circ},\; +5^{\circ}).
$$

3. Solves the **reactive** system with the fixed factorization
   $\mathbf{L}_Q\mathbf{U}_Q = \mathbf{B''}_{PQ}$ and scales by the current
   voltage magnitude:

$$
\Delta |V| = \operatorname{clip}\!\left( |V|_{PQ} \odot
\left(\mathbf{B''}_{PQ}^{-1}\, \Delta Q_{PQ}\right),\; -\Delta V_{max},\; +\Delta V_{max}\right),
$$

   with $\Delta V_{max}$ = `max_voltage_step` (default 0.05 p.u.). The scaling by
   $|V|$ makes the correction a per-unit voltage step; at flat voltage
   ($|V|\approx 1$) it coincides with the classical $\Delta Q/|V|$ form.

4. Applies both steps and **damps** them with a backtracking line search
   (`_damped_step`): starting from $\mu=1$, the step is halved up to 16 times
   until the combined mismatch is no larger than the current residual,

$$
\theta^{(k+1)} = \theta^{(k)} + \mu\,\Delta\theta,
\qquad
|V|^{(k+1)} = |V|^{(k)} + \mu\,\Delta|V|,
$$

   and the trial magnitudes stay within the bus feasibility band
   $\max(0.4,\ 0.8 V_{min}) \le |V| \le \max(2.0,\ 1.5 V_{max})$.

The alternation between one active solve and one reactive solve per iteration is
the classic **1P–1Q** fast-decoupled scheme.

### 2.4 Convergence and divergence

The residual is

$$
R = \max\left( \max_{i\in PV\cup PQ} |\Delta P_i|,\;
\max_{i\in PQ} |\Delta Q_i| \right),
$$

and convergence is declared when $R \le \varepsilon$, with
$\varepsilon = \min(\mathrm{TEPA}, \mathrm{TEPR})/S_{base}$ as in the
Newton-Raphson solver. The iteration fails (`diverged=True`) if the step
produces non-finite voltages or any magnitude leaves $[0.4,\, 2.0]$ p.u.

### 2.5 Computational cost

Because $\mathbf{B'}$ and $\mathbf{B''}$ are factored **once** per solve with
`scipy.sparse.linalg.factorized` (a sparse LU), every subsequent iteration is
just two triangular solves. The FD solver is therefore several times faster per
iteration than the full Newton-Raphson method and is the default fast solver
for large, well-behaved cases.

## 3. Fast-decoupled for the Brazilian PWF cases

The FD solver shares the full `o-grid` convergence strategy with the
Newton-Raphson path:

* **Case construction** from `DBAR`/`DLIN`/`DGER`/`DCER`/`DCSC`/`DCNV`/`DCLI`/
  `DELO`/`DCCV`/`DBSH` records (see NEWTON-RAPHSON.md §3.1),
* **Settings** from the PWF constants (`TEPA`, `TEPR`, `ACIT`, `VDVN`, `VDVM`,
  `ASTP`, `VSTP`, `ZMIN`) and activated `DOPC` options,
* **Switch/jumper network reduction** (`reduce_closed_switches`), which also
  removes the near-zero-impedance branches that would otherwise destroy the
  decoupled approximation,
* **Island reference-bus assignment**, and
* the **outer control loop** (bus limits → SVC → switched shunt → LTC → LCC)
  with Y-bus rebuild and re-solve after every accepted control change.

The step clamps are what make FD robust on the Brazilian network: the
$\pm 5^{\circ}$ angle clamp and the $\pm\Delta V_{max}$ voltage clamp keep the constant
matrices from producing wild corrections when a control change temporarily
pushes the system far from the operating point.

### 3.1 Newton-Raphson fallback

If the FD iteration exhausts `ACIT` iterations without converging,
`solver.py` **retries the whole base solve with the full Newton-Raphson method**,
seeded with the last decoupled voltage state, and marks the run
`fallback_used = True`:

```text
Fast-decoupled power flow did not converge; retrying with Newton-Raphson
from the decoupled voltage state.
```

This guarantees that a case which is too stiff for the decoupled approximation
(e.g. heavily loaded corridors or strong $P$–$V$ coupling) still converges. The
convergence trace of the fallback is reported in the live iteration log.

### 3.2 LCC/HVDC cases always use Newton-Raphson

Cases containing line-commutated converters (`LCCData`, i.e. the `DCNV`/`DCLI`
HVDC links of the Brazilian system) are solved with Newton-Raphson **even when
the fast-decoupled solver is requested**, because the DC link couples active and
reactive power at the converter buses, which the decoupled approximation does
not capture well. The run is marked `fallback_used = True` in this case too.

## 4. Control and device models in `acpf/models/`

The FD path uses exactly the same device models as the Newton-Raphson path.
Their equations are described in full in NEWTON-RAPHSON.md §4; this section
summarizes where each one acts and how that interacts with the decoupled
matrices.

### 4.1 `case.py` — `PowerFlowCase`, `BusData`, `BranchData`

The same numerical case model. The index sets (`slack_indices`,
`pv_indices`, `pq_indices`) define which rows of $\mathbf{B'}$ and
$\mathbf{B''}$ are factored, and `specified_power` supplies the mismatch
right-hand sides. Note that the FD matrices are built from $\mathbf{Y}$ **after**
`reduce_closed_switches` and after `build_ybus`, so they automatically include
the reduced topology, taps, phase shifts, and shunts.

### 4.2 `utils/network.py` — `build_ybus`

Produces the $\mathbf{Y}$ from which both constant matrices are derived:
$\mathbf{B'} = \mathbf{B''} = -\operatorname{Im}(\mathbf{Y})$. Because the
matrices are constant, any control change that modifies $\mathbf{Y}$ (SVC
injection does not, but switched-shunt susceptance and LTC taps do) forces the
solver to **rebuild and re-factor** $\mathbf{B'}$, $\mathbf{B''}$, which is
exactly what the outer control loop in `solver.py` does before every re-solve.

### 4.3 `settings.py` — `PowerFlowSettings`

Supplies the FD-specific step limits `max_angle_step` (from `ASTP`, default
$\max(5^{\circ},|\mathrm{ASTP}|)$) and `max_voltage_step` (from `VSTP`×0.01), plus the
shared tolerances and divergence bounds. `max_csc_step` (`CSTP`) and
`low_impedance_threshold` (`ZMIN`) are read here as well.

### 4.4 `svc.py` — `SVCData`, `adjust_svc_reactive_power`

The SVC droop (see NEWTON-RAPHSON.md §4.4) updates the reactive injection
$Q = (V_{ref}-V_{ctrl})/X_s \cdot V_{bus}\, S_{base}$ clipped to
$[Q_{min}V^2,\, Q_{max}V^2]$ at the SVC's PQ bus. Since this is a *specified
injection* change rather than a network change, the FD matrices are unchanged;
only the mismatch right-hand side $\Delta Q$ reflects it on the next solve.

### 4.5 `shunt.py` — `ShuntControlData`, `adjust_switched_shunts`

Bang-bang capacitor/reactor control. Switching a bank changes the bus shunt
susceptance $b^{sh}$, which **modifies the diagonal of $\mathbf{Y}$ and hence
$\mathbf{B''}$**, so the reactive matrix must be rebuilt before the next FD
solve. In practice the control pass re-runs `build_ybus` and re-factors both
matrices.

### 4.6 `ltc.py` — `adjust_ltc_taps`

LTC tap adjustment $a^{(new)} = \operatorname{clip}(a \pm 0.5(V_{t}-V_{c}),\,
a_{min},\,a_{max})$ with a $\pm 1\%$ step cap. Taps enter the network through
the complex tap $t = a e^{j\phi}$ in $\mathbf{Y}$, so a tap change also
invalidates both FD matrices and triggers a rebuild.

### 4.7 `pst.py` — `apply_pst_to_branch`

Phase-shifting transformers stamp a fixed shift $\phi = -\mathrm{radians}(\phi_{PWF})$
into the branch's complex tap. The decoupled approximation assumes small angles;
a large fixed PST shift is handled by the matrices directly (they are exact
susceptances), and the shift is never changed by the FD iteration itself.

### 4.8 `csc.py` — `apply_csc_to_branches`, `is_active_csc`

Series compensation is applied statically at case build time by adding
$j x_{csc}$ to a branch's series reactance (or creating a purely reactive
branch). This changes the series admittance $y = 1/(r + j(x+x_{csc}))$ and thus
both $\mathbf{B'}$ and $\mathbf{B''}$; CSC reactance is *not* adjusted by the FD
loop (the `CSTP` step limit is reserved for future dynamic CSC control).

### 4.9 `lcc.py` — `LCCData`, `update_lcc_from_dc_solution`

HVDC links participate in the control loop exactly as in the Newton-Raphson
path (see NEWTON-RAPHSON.md §4.9): constant-current DC operating point, damping
$\lambda=0.3$, overlap-angle and converter-tap updates, and terminal injections
applied to the AC buses. As noted in §3.2, **cases with LCCs are routed to the
Newton-Raphson solver regardless of the requested FD solver.**

### 4.10 `controls.py` — QLIM and VLIM

The irreversible `PV↔PQ` bus-type conversions are applied on the first control
pass. They change which rows/columns of $\mathbf{B'}$ and $\mathbf{B''}$ are
factored (the $PQ$ set shrinks/grows), so the matrices are rebuilt after the
conversion. `VLIM` additionally pins $|V|$ of converted buses, which fits the
decoupled reactive system naturally.

### 4.11 `network_reduction.py` — `ReducedPowerFlowCase`

Contraction of switches and jumper buses (§3, NEWTON-RAPHSON.md §3.3). This is
particularly important for FD: a contracted network has a **better-conditioned
$\mathbf{B''}$** and fewer near-singular rows, so the constant matrices stay
factorizable for the whole iteration.

### 4.12 `solution.py`, `results.py`, `result_builder.py`

The FD path produces the same `NumericalSolution`, `ACPowerFlowResult`, and
infrasys result components as the Newton-Raphson path, including the
`fallback_used` flag that records when a Newton-Raphson fallback (or LCC
delegation) took place.

## 5. Orchestration in `solver.py`

`FastDecoupledPowerFlow.run` differs from the Newton-Raphson run only in the
base solve and the fallback:

```text
1. build PowerFlowCase + PowerFlowSettings from the parsed system
2. reduce_closed_switches(case)                 # contract switches/jumpers
3. ybus = build_ybus(case); assign_island_reference_buses(case, ybus)
4. if case contains LCCs:
      base solve = solve_newton_raphson(...);  fallback_used = True
   else:
      base solve = solve_fast_decoupled(...)   # B' = B'' = -Im(Y)
5. control loop (up to 12 passes), in order:
     a. bus limits (QLIM/VLIM)            — pass 0 only
     b. adjust_svc_reactive_power
     c. adjust_switched_shunts
     d. adjust_ltc_taps
     e. update_lcc_from_dc_solution
   every accepted change: rebuild ybus, re-factor B', B'', re-solve;
   reject and restore the previous solution if the re-solve fails
6. if the base (or final) FD solution did not converge:
      retry with solve_newton_raphson(...) from the FD voltage state
      fallback_used = True
7. sync_control_state back to the full case
8. expand_voltage to the original topology
9. build results; attach solved values to the infrasys system
```

The `FastDecoupledPowerFlow` class is a drop-in replacement for
`NewtonRaphsonPowerFlow`; both attach the same result components and statistics,
and both honor `print_iterations=True` for the live convergence trace.

## References

* Stott, B., Alsac, O., "Fast Decoupled Load Flow," *IEEE Trans. Power App.
  Syst.*, vol. PAS-93, 1974.
* Stott, B., "Review of Load-Flow Calculation Methods," *Proc. IEEE*, vol. 62,
  1974.
* ANAREDE power-flow manual (program constants `TEPA`, `TEPR`, `ACIT`, `VDVN`,
  `VDVM`, `ASTP`, `VSTP`, `CSTP`, `ZMIN`; options `QLIM`, `VLIM`).
