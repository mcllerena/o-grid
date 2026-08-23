# DC optimal power flow

`DCOptimalPowerFlow` solves a linearized DC optimal power-flow (DC-OPF) model
with the open-source HiGHS linear-programming solver. The implementation calls
`scipy.optimize.linprog(method="highs")`; the `highspy` package is also a
runtime dependency when applications need the native HiGHS Python API.

## Optimization model

The decision variables are active generator outputs $p_g$ and bus voltage
angles $\theta$. Quantities in the LP are per unit on the case base power
$S_{base}$; generator limits and branch ratings are converted from MW before
the solve. The objective is a linear generation-cost model:

$$
\begin{aligned}
\min_{p_g,\theta}\quad & c^T p_g \\
	ext{where}\quad & c_g = c_{1,g} + 2c_{2,g}p^{init}_g.
\end{aligned}
$$

For generator $g$ at bus $i$, its output is bounded by

$$
\underline p_g \leq p_g \leq \overline p_g.
$$

For each bus $i$, active-power balance is

$$
\sum_{g\in\mathcal{G}_i}p_g - p_{d,i} - \gamma_i
= \sum_{(i,j)\in\mathcal{E}}\left[b_{ij}(\theta_i-\theta_j)+\rho_{ij}\right],
$$

where an incident branch contributes with its orientation: a branch entering
bus $i$ contributes the negative of its stored flow expression. The directed
flow from branch `from_bus` $i$ to `to_bus` $j$ is

$$
f_{ij}=b_{ij}(\theta_i-\theta_j)+\rho_{ij}.
$$

When branch limits are enabled, each directed flow satisfies

$$
-\overline f_{ij}\leq f_{ij}\leq\overline f_{ij},
\qquad
\overline f_{ij}=\frac{\text{rating}_{ij}}{S_{base}}.
$$

The angle of every parsed reference/slack bus is fixed to its input value. All
other angles are bounded to $[-\pi,\pi]$ to keep the LP numerically bounded.
The model is solved by HiGHS and the resulting angles, injections, and branch
flows are attached to the parsed system as power-flow results.

Set `enforce_branch_limits=False` only to determine whether infeasibility is
caused by the parsed ratings. That mode is an unconstrained-dispatch
diagnostic, not a thermally constrained OPF solution.

## Parameterization approaches

The `param_opt` argument supports the four parameterizations from Taheri and
Molzahn (arXiv:2410.11725):

### `cold_start`

Uses the physical line coefficient derived from branch resistance $r$,
reactance $x$, and tap ratio $\tau$:

$$
b_{ij}=\frac{x_{ij}}{r_{ij}^2+x_{ij}^2}\frac{1}{\tau_{ij}},
\qquad \gamma_i=0,
\qquad \rho_{ij}=-b_{ij}\phi_{ij},
$$

where $\phi_{ij}$ is the branch phase shift. This is the default mode.

### `hot_start`

Starts with the cold-start coefficients, then fits each $b_{ij}$ and
$\rho_{ij}$ to the parsed nominal AC branch flow and input angle difference.
The bus bias is fitted to the nominal AC injection mismatch:

$$
b_{ij}=\frac{f^{AC}_{ij}}{\theta_i-\theta_j},
\qquad
\rho_{ij}=f^{AC}_{ij}-b_{ij}(\theta_i-\theta_j),
$$

when the nominal angle difference is nonzero, and $\gamma_i$ absorbs the
remaining nominal bus mismatch.

### `dcpf`

Uses the conventional lossless DCPF coefficient:

$$
b_{ij}=\frac{1}{x_{ij}\tau_{ij}},
$$

with zero bus bias and the cold-start phase-shift bias. This mode is a DCPF
linearization used inside the optimization model; it is still an LP because
generator outputs and operating constraints are optimized.

### `optimal`

The optimal approach learns the linearization parameters offline over a set of
representative operating scenarios $\mathcal{S}$. For scenario $s$, let
$p^{AC\text{-}OPF}_s$ be the generator setpoints from the reference AC-OPF and
$p^{DC\text{-}OPF}_s(b,\gamma,\rho)$ be the generator setpoints returned by the
linear DC-OPF. The upper-level fitting problem is:

$$
\begin{aligned}
\min_{b,\gamma,\rho}\quad
& \frac{1}{|\mathcal{S}|}\sum_{s\in\mathcal{S}}
\left\|p^{DC\text{-}OPF}_s(b,\gamma,\rho)
	-p^{AC\text{-}OPF}_s\right\|_2^2 \\
	ext{subject to}\quad
& p^{DC\text{-}OPF}_s(b,\gamma,\rho) \\
&\qquad\in \operatorname*{argmin}_{p_g,\theta}\ c^T p_g,
\quad \forall s\in\mathcal{S}.
\end{aligned}
$$

The lower-level problem in this bilevel formulation is the DC-OPF defined
above, with scenario-specific loads, generator bounds, reference angles, and
branch ratings. The learned parameters replace the physical coefficients in
the branch-flow and nodal-balance equations:

$$
f_{ij}^{optimal}=b_{ij}^{optimal}(\theta_i-\theta_j)+\rho_{ij}^{optimal},
$$

$$
\sum_{g\in\mathcal{G}_i}p_g-p_{d,i}-\gamma_i^{optimal}
=\sum_{(i,j)\in\mathcal{E}}f_{ij}^{optimal}.
$$

This repository currently implements the online lower-level solve. It accepts
the learned values through `DCOPFParameters(b=..., gamma=..., rho=...)`; it
does not run the offline bilevel training or produce those values automatically.
The online lower-level DC-OPF is solved by HiGHS:

```python
from o_grid import DCOPFParameters, DCOptimalPowerFlow

parameters = DCOPFParameters(b=branch_b, gamma=bus_gamma, rho=branch_rho)
run = DCOptimalPowerFlow(
	param_opt="optimal",
	parameters=parameters,
).run(system)
```

```python
from o_grid import DCOptimalPowerFlow

run = DCOptimalPowerFlow(param_opt="hot_start").run(system)
assert run.result.converged
```
