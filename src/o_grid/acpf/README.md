# Newton Power Flow

The Newton power flow is used to compute initial conditions for dynamic
simulations, generation redispatch, and steady-state contingency analyses.
The full Newton approach solves all controls simultaneously, including
generators, controlled shunts, transformer taps, phase shifters, and DC links.
It was selected because it is more reliable than approaches that solve these
controls sequentially.
## Newton Power Flow

The Newton power flow is used to compute initial conditions for dynamic
simulations, generation redispatch, and steady-state contingency analyses.
The full Newton approach solves all controls simultaneously, including
generators, controlled shunts, transformer taps, phase shifters, and DC links.
It was selected because it is more reliable than approaches that solve these
controls sequentially.

The DC power flow is used only for initialization and steady-state contingency
screening. The following techniques improve the Newton method's convergence
properties:

- The correction vector is scaled at each iteration to avoid excessively large
  state variations.
- When a controlled voltage setpoint changes, the voltages at neighboring buses
  connected by low-impedance branches are reinitialized.
- The Jacobian is better conditioned through a special diagonal stabilization
  approach.
- Constant-power and constant-current loads can optionally be converted into
  constant-impedance loads at very low voltage levels.
- Voltage-control sharing and priority among multiple devices, such as
  generators, shunts, and taps, are modeled to avoid solution arbitrariness and
  convergence flip-flop.
- For contingencies, automatic rescue strategies distinguish a true lack of a
  solution from a numerical problem. These include gradual transitions from
  pre-contingency to post-contingency states and, when necessary, submission of
  the case to the synthetic dynamic power-flow solver.

## Formulation

The formulation is based on Kirchhoff's current law at every bus. In terms of
power equations, the generation minus the load must equal the power flowing
through the branches connected to the bus. This is expressed as:

$$
0 = P_{g,k} - P_{l,k} - \sum_{m \in \Omega_k} P_{k,m}
\qquad\qquad\qquad\mathrm{(6.1)}
$$

$$
0 = Q_{g,k} - Q_{l,k} + Q_{cap,k} - Q_{rea,k}
    - \sum_{m \in \Omega_k} Q_{k,m}
\qquad\qquad\qquad\mathrm{(6.2)}
$$

for $k = 1, \ldots, N$, where $k$ is a generic bus index, $\Omega_k$ is the
set of buses adjacent to bus $k$, and $N$ is the total number of buses.

These equations are nonlinear functions of the following variables:

- voltage magnitude $V_k$ and angle $\theta_k$ for every bus;
- transformer tap ratio $a_{k,m}$ and phase-shift angle $\phi_{k,m}$;
- bus generation $P_{g,k}$ and $Q_{g,k}$; and
- bus load $P_{l,k}$ and $Q_{l,k}$.

The full Newton-Raphson method solves all controls, including HVDC, OLTC, and
remote voltage control, within the Newton iteration. Newton step control is
also adopted.

The equations and variables can be formulated as a general problem of finding
the solution of a set of nonlinear equations:

$$
0 = f(x)
\qquad\qquad\qquad\mathrm{(6.3)}
$$

where $f(x)$ is a multidimensional function of the dependent variables
$x = (V, \theta, a, \phi)$.

The Newton-Raphson method is an effective approach for solving Equation (6.3).
Its success is mainly due to its convergence properties and simple
implementation. It is based on the truncated Taylor series:

$$
f(x + \Delta x) \approx f(x) + f'(x)\Delta x,
$$

where $f'(x)$ is the Jacobian matrix. At the solution,
$f(x + \Delta x) = 0$, so:

$$
\Delta x = -\left(\frac{\partial f(x)}{\partial x}\right)^{-1} f(x)
         = -J^{-1}f(x).
\qquad\qquad\qquad\mathrm{(6.4)}
$$

The method solves the following equations in one or more iterations:

$$
\Delta x_i = -[J(x_i)]^{-1}f(x_i)
\qquad\qquad\qquad\mathrm{(6.5)}
$$

$$
x_{i+1} = x_i + \Delta x_i.
\qquad\qquad\qquad\mathrm{(6.6)}
$$

Iterations continue until $f(x_i) < \varepsilon$, where $i$ is the iteration
counter and $\varepsilon$ is a small tolerance.

To improve convergence, the Newton step can be corrected as follows:

$$
x_{i+1} = x_i + \alpha_i \Delta x_i.
\qquad\qquad\qquad\mathrm{(6.7)}
$$

For well-behaved cases, the factor $\alpha_i$ is approximately one. For
ill-conditioned cases, it is usually less than one.

All controls, including HVDC, OLTC, and remote voltage control, are solved
within the Newton iteration.


## Calculated Mvar Limits

Mvar limits can optionally be computed using the following expressions.

### Maximum stator current

$$
I_{s,\max} = \pm\sqrt{(S_{\mathrm{MVA}} \cdot SF)^2 - P^2}
$$

Here, $SF$ is the stator-current service factor.

### Maximum rotor current

The maximum rotor current under the excitation limit is:

$$
I_{r,\max} = \left(\sqrt{(V E_{q\max})^2 - (X_s P)^2 - V^2}\right) \frac{1}{X_s}
$$

The under-excitation reactive-power limit is:

$$
Q_l = \frac{P}{\tan(\delta_{\max})} - \frac{V^2}{X_s}
$$

Here, $X_s$ is the synchronous reactance (or quadrature reactance),
$\delta_{\max}$ is the maximum loading angle, and $SF$ is the stator current service factor.

## Power-Flow VSC Multiterminal Model

The following equations describe the converter configuration. The apparent
power at the sending terminal is:

$$
S_s = P_s + jQ_s
$$

The terminal power-flow equations are:

$$
P_{sf} = -V_s^2G_t - V_sV_f
\left[G_t\cos(\delta_s - \delta_f) + B_t\sin(\delta_s - \delta_f)\right]
$$

$$
Q_{sf} = -V_s^2B_t - V_sV_f
\left[G_t\sin(\delta_s - \delta_f) - B_t\cos(\delta_s - \delta_f)\right]
$$

$$
P_{cf} = V_c^2G_c - V_cV_f
\left[G_c\cos(\delta_c - \delta_f) + B_c\sin(\delta_c - \delta_f)\right]
$$

$$
Q_{cf} = -V_c^2B_c - V_cV_f
\left[G_c\sin(\delta_c - \delta_f) - B_c\cos(\delta_c - \delta_f)\right]
$$

$$
Q_f = -V_f^2B_f
$$

The relation between AC and DC voltages for a six-pulse IGBT converter is:

$$
V_c = \frac{\sqrt{3}}{2\sqrt{2}}m_aV_{dc}e^{j\delta_c}
$$

For linear or square-wave modulation, it is:

$$
V_c = \frac{\sqrt{6}m_aV_{dc}}{\pi}e^{j\delta_c}
$$

Here, $V_{dc}$ is the voltage across the poles and $m_a$ is the voltage
magnitude modulation factor. It is equal to $1$ for square-wave modulation
and less than $1$ for a PWM modulation level or multilevel arrangement. The AC
voltage angle is controlled through $\delta_c$.

### Losses

The losses are modeled by the following quadratic function.

$$
P_{\mathrm{loss}} = a + bI_c + cI_c^2
$$

where

$$
I_c = \frac{\sqrt{P_c^2 + Q_c^2}}{\sqrt{3}V_c}
$$

### Current Limit

The current limit is specified as $I_{c\max}$. However, it is convenient to
define the maximum power as a function of the maximum current, as follows.

$$
\overline{S}_s = \overline{V}_s\,\overline{I}_s^{\,*}
$$

with

$$
\overline{V}_s = \overline{V}_f - \overline{Z}_t\,\overline{I}_s
$$

and

$$
\overline{I}_s = \overline{I}_c - \frac{\overline{V}_s + \overline{Z}_t\,\overline{I}_s}{jB_f}
$$

It follows that

$$
\overline{S}_s = -V_s^2
\left(\frac{1}{-jB_f + \overline{Z}_t}\right)
 + \overline{V}_s\,\overline{I}_{c\max}^{\,*}
\left(\frac{-jB_f}{-jB_f + \overline{Z}_t}\right)
$$

### Reactive Power Limit

For VSC converters that use PWM, the modulation factor has upper and lower
limits to avoid overmodulation and consequently high harmonic components. As a
consequence, the maximum and minimum reactive-power limits are fixed (for
example, $\pm 0.5$ p.u.).

### Voltage Limit

With modular multilevel converter (MMC) technology, the reactive power is
limited by the current in the inductive region. The lower voltage limit can be
omitted in this case. It can be computed as:

$$
\overline{S}_s = -V_s^2
\left(\overline{Y}_1^{\,*} + \overline{Y}_2^{\,*}\right)
 + \overline{V}_s\,\overline{V}_{cm}^{\,*}\,\overline{Y}_2^{\,*}
$$

Here, $\overline{V}_{cm}$ can represent $\overline{V}_{cm\min}$ or
$\overline{V}_{cm\max}$. The value $\overline{V}_{cm\max}$ is the maximum AC
voltage without overmodulation. The lower limit $\overline{V}_{cm\min}$ can
be specified to comply with the minimum reactive power. This limit can be
omitted for MMC converters or whenever no reactive limit is imposed on the
converter.

### DC Network

The DC injection current of each converter is given by

$$
I_{dci} = \sum_{\substack{j=1 \\ j \ne i}}^N
G_{ij}\left(V_{dci} - V_{dcj}\right)
$$

where

$$
G_{ij} = \frac{1}{R_{ij}}
$$

This leads to the following matrix form:

$$
I_{dc} = G_{dc}V_{dc}
$$

### Voltage Base

As usual, the power base is the same for the entire system. Therefore,
determining the per-unit values for the DC side requires that the base voltage
or current be specified. Also as usual, we choose to specify the nominal
voltage value.

The voltage between poles in a converter with linear pulse modulation is given
by

$$
V_{dc} = \frac{2\sqrt{2}}{\sqrt{3}}\,n\,m_aV_{ac,rms}
$$

In the case of multilevel and square-wave converters, the relationship is

$$
V_{dc} = \frac{\pi\sqrt{2}}{2\sqrt{3}}\,n\,m_aV_{ac,rms}
$$

Here, $V_{ac,rms}$ is the voltage base at the AC side, $n$ is the number of
converters in series, and $m_a$ is the modulation factor. Thus, a common base
DC voltage value for both types of converters is given by the line peak voltage
(phase-to-phase):

$$
V_{dc,\mathrm{base}} = n\sqrt{2}\,V_{ca,\mathrm{base}}
$$

Therefore, $m_a$ is set to establish the DC voltage value in p.u. specified to
the converter. This is the value for one pole. For the bipole, the voltage is
divided by $2$.
