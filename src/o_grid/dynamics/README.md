# Reduced-order dynamic stability

The `o_grid.dynamics` package provides three related capabilities:

- lossless, structured parsing of ANAREDE dynamic-model files (`.dyn`);
- lossless, typed parsing of ANAREDE dynamic-contingency files (`.evt`); and
- a reduced-order transient and small-signal stability study.

The stability study is deliberately smaller than a full transient-stability
program. It runs a static NTW power flow, initializes one classical swing
machine for each usable `SMxx` dynamic model, and integrates independent swing
equations. AVR, governor, PSS, inverter, detailed network algebraic states, and
topology-changing branch models are not simulated.

## End-to-end approach

`StabilityStudy.run()` follows this sequence:

1. Load the NTW network and DYN/EVT files, unless already-parsed objects were
	supplied.
2. Run `NewtonRaphsonPowerFlow(max_control_passes=0)` unless a custom solver
	was supplied. A non-converged power flow aborts initialization.
3. Match each dynamic model whose identifier begins with `SM` to a static
	`Generator` at the same bus and to a solved power-flow bus.
4. Read inertia and damping from the first later DYN record containing at least
	15 values.
5. Initialize each rotor angle from the solved bus angle and each speed
	deviation to zero.
6. Integrate the swing equations with SciPy `solve_ivp`, using `rtol=1e-7` and
	`atol=1e-9`.
7. Calculate trajectories, independent-machine eigenvalues, and the stability
	flag in a `StabilityResult`.

The simulation time vector is generated as

$$
t_k = k\,\Delta t,\qquad
0\leq t_k\leq T,
$$

where $T$ is `StabilityConfig.duration` and $\Delta t$ is
`StabilityConfig.time_step`. The endpoint is included when it falls within the
half-step tolerance used by the implementation.

## Classical swing model

For machine $m$, the state is rotor angle $\delta_m$ and speed deviation
$\omega_m$. The code integrates

$$
\frac{d\delta_m}{dt}=\omega_m,
$$

$$
\frac{d\omega_m}{dt}
=\frac{P_{m,m}-P_{e,m}(\delta_m,t)-D_m\omega_m}{2H_m},
$$

where:

- $H_m$ is the non-negative inertia value, clamped to at least $0.05$;
- $D_m$ is the non-negative damping value;
- $P_{m,m}$ is the static generator active power divided by the power-flow
  base MVA; and
- $P_{e,m}$ is the event-scaled electrical power.

The electrical power approximation is

$$
P_{e,m}(\delta_m,t)=K_m\,P^{max}_m\sin(\delta_m),
$$

where $K_m$ is the aggregate network factor described below. The machine
power-angle limit is initialized from the static operating point:

$$
s_m=\max\left(|\sin(\delta_{m,0})|,0.1\right),
$$

$$
P^{max}_m
=\max\left(\frac{|P_{m,m}|}{s_m},1.2|P_{m,m}|,0.1\right).
$$

Initial conditions are

$$
\delta_m(0)=\delta_{m,0},\qquad \omega_m(0)=0.
$$

The implementation does not use `frequency_hz` in the differential equation;
that setting is validated as part of the public configuration and remains
available for a future model with frequency-dependent states.

## Disturbance and event logic

Without an EVT contingency, the scalar network factor is

$$
K(t)=
\begin{cases}
K_{fault}, & t_{fault}\leq t<t_{clear},\\
K_{post}, & \text{otherwise}.
\end{cases}
$$

These values are `fault_factor` and `post_fault_factor`. The interval is
left-closed and right-open.

With an EVT contingency, the factor starts at `post_fault_factor` and events
are applied in file order when `event_time <= t`:

| Event types | Network-factor action |
| --- | --- |
| 3, 4 | Set factor to `fault_factor`. |
| 5, 6, 8 | Set factor to `post_fault_factor`. |
| 7, 9, 10, 11 | Set factor to the smaller of its current value and `0.8 * post_fault_factor`. |
| Other types | Preserve the current factor. |

This is an aggregate approximation. The EVT parser preserves all event fields,
but the current study does not mutate branches, buses, shunts, generators, or
controllers in response to individual event records.

## Small-signal analysis

The study linearizes each machine independently around its initial angle. For
machine $m$, define

$$
S_m=P^{max}_m\cos(\delta_{m,0}),\qquad
d_m=\frac{D_m}{2H_m},\qquad
k_m=\frac{S_m}{2H_m}.
$$

The reported eigenvalues are the roots of

$$
\lambda^2+d_m\lambda+k_m=0.
$$

There are two eigenvalues per initialized machine. The result is marked stable
only when every eigenvalue has a strictly negative real part and every sampled
rotor angle remains below $\pi$ radians in absolute value:

$$
\operatorname{stable}
=\left(\forall\lambda: \Re(\lambda)<0\right)
\land
\left(\max_{m,t}|\delta_m(t)|<\pi\right).
$$

`StabilityResult.maximum_angle` reports the second quantity. Its
`damping_ratios` property computes

$$
\zeta_i=-\frac{\Re(\lambda_i)}{|\lambda_i|},
$$

with non-finite values replaced by zero.

## DYN file parsing

`DynFileParser` requires a first non-empty `VERSION` declaration. A model starts
with a case-insensitive `SM` followed by digits, for example `SM04`. Comment
lines beginning with `!` are stored as headers for the following record. Every
non-comment data line becomes a `DynDataRecord`; values that parse as floats are
stored as `float`, and identifiers remain strings. The parser preserves source
line numbers and raw record text in `DynFile`, `DynModel`, and `DynDataRecord`.

```python
from pathlib import Path

from o_grid.dynamics import DynFileParser

dynamic_file = DynFileParser(Path("case.dyn")).file
for model in dynamic_file.models:
	 print(model.model, model.name, model.start_line)
	 for record in model.records:
		  print(record.line_number, record.values, record.raw)
```

## EVT file parsing

`EvtFileParser` reads the total simulation time, contingency headers, ten-field
event records, `-99` contingency terminators, and the `-999` file terminator.
Event parameter 3 is exposed as `DynamicEvent.event_time`. Bus references may
be numeric or text, and the parser preserves the raw line and source line
number. It validates record shape and numeric fields but intentionally leaves
event-specific physical behavior to `StabilityStudy`.

```python
from pathlib import Path

from o_grid.dynamics import EvtFileParser

event_file = EvtFileParser(Path("case.evt")).file
for contingency in event_file.contingencies:
	 print(contingency.number, contingency.identifier.strip())
	 for event in contingency.events:
		  print(event.event_type, event.bus_1, event.bus_2, event.event_time)
```

## Running a study

```python
from pathlib import Path

from o_grid.dynamics import StabilityConfig, StabilityStudy, plot_stability_result

study = StabilityStudy(
	 Path("case.ntw"),
	 Path("case.dyn"),
	 event_file=Path("case.evt"),
	 contingency=2,
	 config=StabilityConfig(duration=10.0, time_step=0.01),
)

power_flow = study.run_power_flow()
result = study.run()
print(result.stable, result.maximum_angle, result.damping_ratios)
figure = plot_stability_result(result)
figure.savefig("stability.png", dpi=150)
```

`contingency` may be a number or an identifier. If an EVT file is supplied and
no selector is given, the first contingency containing events is selected. If
no event file is supplied, the configured temporary fault interval is used.

## Scope and limitations

The output is useful for exercising a reduced-order transient-stability
workflow and comparing event-factor scenarios. It is not a full network
transient-stability result: the machines are independent, the network is
represented by one scalar factor, and no detailed device or topology dynamics
are solved. Use the preserved DYN/EVT records as the extension point for a
future full-order algebraic-differential model.
