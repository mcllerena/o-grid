# Data-center allocation and siting

This package implements ReEDS-style, multi-period capacity expansion for large electrical loads and co-located generation. Planning is intentionally separate from AC validation:

1. `CapacityExpansionStudy` defines cumulative load milestones, eligible buses, site limits, generation ratios, interconnection, transmission projects, and costs.
2. `solve_capacity_expansion()` solves the compact Pyomo MILP with HiGHS.
3. The selected plan is materialized as a concrete network case and checked with continuous ACOPF at a selected year.

## Planning milestones

`cumulative_load_mw_by_year` contains total installed capacity by the end of each year, not annual additions:

```python
cumulative_load_mw_by_year={2030: 50.0, 2035: 100.0}
```

This installs 50 MW by 2030 and 50 additional MW between 2030 and 2035, reaching 100 MW cumulatively.

## How the bus is picked

`candidate_buses` is an explicit eligibility set. The model does not automatically inspect every PWF bus, rank bus names, or discover a site from the ACOPF. Only buses listed in `candidate_buses` can receive capacity.

The large-scale example uses:

```python
candidate_buses=(10,)
max_sites=1
```

Bus 10 is selected because it is the only eligible bus and the one-site constraint requires it to be activated. The choice is represented by the binary `SITE_ACTIVE[b]` variable and is read from `plan.site_active` after HiGHS solves the planning model.

With multiple candidates, the model chooses activated buses that can satisfy every cumulative target while respecting `max_sites`, bus capacity limits, interconnection capacity, selected transmission projects, and investment costs. If candidates have identical costs and constraints, they are equivalent optima and HiGHS may choose any of them. Use bus-specific costs or limits to express a siting preference.

The ACOPF stage receives the selected bus as fixed input. It validates the planning decision rather than repeating a binary siting search inside a nonlinear model.

## Formulation

Let $B$ be the candidate-bus set and $Y$ the ordered planning-year set. For each bus $b$ and year $y$, the model uses load investment $I^L_{b,y}$, cumulative load $C^L_{b,y}$, active-generation investment $I^G_{b,y}$, cumulative active generation $C^G_{b,y}$, reactive-generation investment $I^Q_{b,y}$, cumulative reactive capability $C^Q_{b,y}$, operational load $O^L_{b,y}$, and binary site activation $z_b$.

### Capacity accounting

$$
C^L_{b,y}=\sum_{k\le y}I^L_{b,k},\qquad
C^G_{b,y}=\sum_{k\le y}I^G_{b,k},\qquad
C^Q_{b,y}=\sum_{k\le y}I^Q_{b,k}.
$$

### Generation and targets

With active and reactive ratios $\alpha$ and $\beta$:

$$
I^G_{b,y}=\alpha I^L_{b,y},\qquad I^Q_{b,y}=\beta I^L_{b,y}.
$$

Every milestone is enforced across all candidates:

$$
\sum_{b\in B}C^L_{b,y}=D_y\qquad\forall y\in Y.
$$

Capacity can be assigned only to an activated site:

$$
C^L_{b,y}\le M_bz_b.
$$

The operational variable is bounded by capacity factor:

$$
\mathrm{CF}\,C^L_{b,y}\le O^L_{b,y}\le C^L_{b,y}.
$$

The current example validates final cumulative capacity as a fixed load; it does not pass hourly values of $O^L$ into ACOPF.

### Objective

The objective minimizes load-site, active-generation, interconnection, and selected transmission-project investment costs. Reactive capability is linked to load but has no separate cost coefficient.

## Interconnection and physical transmission

Existing and expandable site interconnection is represented by:

$$
C^{IC}_{b,y}=E_b+\sum_{k\le y}I^{IC}_{b,k}
+\sum_{p:b(p)=b}K_p\sum_{k\le y}x_{p,k},
$$

where $E_b$ is existing capacity, $I^{IC}$ is abstract interconnection expansion, $K_p$ is project capacity, and binary $x_{p,y}$ builds project $p$ in year $y$. Each project can be built at most once:

$$
\sum_yx_{p,y}\le1.
$$

A project is unavailable before `available_year`; its cost is included in the objective. Site capacity must fit the resulting connection:

$$
C^L_{b,y}\le C^{IC}_{b,y}.
$$

`apply_transmission_expansion()` converts selected projects into fixed `BranchData` objects. It validates endpoint buses and duplicate circuits, copies the project impedance, charging, and rating, and returns a new `PowerFlowCase` without mutating the parsed case. This is the handoff that makes a planning reinforcement visible to AC equations.

## Large-system convergence workflow

The large-scale workflow is decomposed into discrete planning and continuous validation:

1. The PWF parser reads the Brazilian case.
2. HiGHS solves the small planning MILP for sites, milestones, interconnection, and candidate projects.
3. Selected projects are appended as physical branches.
4. The final cumulative load is applied to the selected bus with the configured power factor.
5. AC preprocessing reduces closed switches and prepares a continuous model.
6. Ipopt solves the nonlinear AC equations without binary site or branch variables.

For the checked-in 7,282-bus case, the run parsed 7,282 buses and 10,750 line records. One 700 MW reinforcement was selected, increasing the case to 10,379 branches before AC preprocessing. The continuous AC model reported 6,912 buses and 9,995 branches, converged in 39 Ipopt iterations in approximately 60 seconds, and returned `Converged: True` with maximum mismatch $4.975205\times10^{-4}$ pu.

Convergence is not the same as universal operating-limit satisfaction. The detailed solver output must still be reviewed for active/reactive residuals, voltage-limit notices, generator limits, and branch limits. The current two-stage implementation does not synthesize corridors from overload sensitivities, perform N-1 expansion, choose generation technologies or vintages, run chronological dispatch, or automatically feed AC violations back into a new planning solve.

## Python API

```python
from o_grid.data_center import CapacityExpansionStudy, solve_capacity_expansion

study = CapacityExpansionStudy(
    candidate_buses=(4, 5, 6),
    cumulative_load_mw_by_year={2030: 50.0, 2035: 100.0},
    generation_mw_per_load_mw=1.0,
    generation_mvar_per_load_mw=0.203,
    max_sites=1,
)
plan = solve_capacity_expansion(study)
```

`CapacityExpansionPlan` returns cumulative load, active-generation, reactive-generation, and interconnection capacities indexed by `(bus, year)`, site activation values, and transmission build decisions indexed by `(project_name, year)`.

See the full explanation at [`docs/src/content/docs/explanation/data-center-siting.mdx`](../../../docs/src/content/docs/explanation/data-center-siting.mdx) and the runnable workflow in `examples/run_data_center.py`.
