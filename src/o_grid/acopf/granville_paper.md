# OPTIMAL REACTIVE DISPATCH THROUGH INTERIOR POINT METHODS

Author: Sergio Granville CEPEL - Centro de Pesquisas de Energia Eletrica Rio de Janeiro, Brazil

Abstract: An implementation of an interior point method to the optimal reactive dispatch problem is described. The interior point method used is based on the primal-dual algorithm and the numerical results in large scale networks (1832 and 3467 bus systems) have shown that this technique can be very effective to some optimal power flow applications.

Keywords: Optimal power flow, optimal reactive dispatch, Interior point methods.

## 1. Introduction

The optimal reactive dispatch (ORD) is a particular case of the optimal power flow problem (OPF) which consists in determining the state of an electric power system which optimizes a given objective function and satisfies a set of physical and operating constraints. Both problems can be formulated as:

$$
\begin{aligned}
\min_{z}\quad & f(z) \\
\mathrm{s.t.}\quad & h(z) = 0, \\
& i \le z \le u, \qquad z \in \mathbb{R}^{n}.
\end{aligned}
\qquad (1)
$$

The functions $f$ and $h$ are continuously differentiable, with

$$
f:\mathbb{R}^{n}\to\mathbb{R},\qquad h:\mathbb{R}^{n}\to\mathbb{R}^{m}.
$$

The vectors $\ell$ and $u$ in $\mathbb{R}^{n}$ are the lower and upper bounds
on the variables, respectively.

The constraints $h(z)=0$ and $\ell\le z\le u$ represent network modeling
and equipment operating limits.

In realistic applications, OPF is a large-scale nonlinear programming problem
with thousands of variables and nonlinear constraints. Since its initial
formulation in the 1960s [1](#ref-1), several methods have been proposed,
including the reduced-gradient method of Dommel and Tinney [2](#ref-2), GRG
[3](#ref-3), the differential-injection method of Carpentier [4](#ref-4), the
projected Lagrangian method [5](#ref-5), sequential quadratic-programming
methods [6](#ref-6), [7](#ref-7), [8](#ref-8), and algorithms based on
sequences of linear or quadratic programming problems [9](#ref-9), [10](#ref-10).

In this paper we consider the application of interior-point methods to ORD.
The field became especially active after Karmarkar's publication of a new
algorithm for linear programming in 1984 [11](#ref-11). Interest in these
methods is due both to their theoretical complexity and to their computational
efficiency. Well-designed implementations can be more attractive than the
simplex method for problems with thousands of variables and constraints
([16](#ref-16)-[18](#ref-18)).

93 WM 238-6 FWRS A paper recommended and approved by the IEEE Power System Engineering Committee of the IEEE Power Engineering Society for presentation at the IEEE/PES 1993 Winter Meeting, Columbus, OH, January 31 - February 5, 1993. Manuscript submitted January 21, 1992; made available for printing November 30, 1992.

linear complementary and convex nonlinear programming, problems as mentioned in [19](#ref-19). However, numerical experiences with interior point methods in nonlinear programming problems seem to be much more limited. Good numerical results have been reported for convex quadratic programming problems ([20](#ref-20),[21](#ref-21)) and separable convex nonlinear programming problems with linear constraints [22](#ref-22). In this latter reference for instance, a sequential quadratic programming algorithm is used and each quadratic progranming subproblem is solved by an interior point algorithm.

With respect to power systems, in [23](#ref-23) a dual-affine algorithm is described to solve a hydro-scheduling problem which is a large scale linear programming problem. In [24](#ref-24) there is a short notice on application of barrier functions to OPF with good numerical results but no implementation details are provided. It is also mentioned in [25](#ref-25) an application of the primal-dual algorithm to the state estimation problem, numerical results with the IEEE 118 bus system is provided.

The interior point algorithm that will be considered here is based on the primal-dual logarithmic barrier method as described by Monteiro and Adler ([26](#ref-26), [27](#ref-27)) for linear and quadratic programming problems. The primal-dual logarithmic barrier method has shown superior computational performance when applied to linear and quadratic programming problems ([16](#ref-16), [17](#ref-17), [18](#ref-18), [21](#ref-21)).

As mentioned before, ORD is a large scale nonlinear programming problem with nonlinear constraints and it is nonconvex. Contrary to the approach adopted in [22](#ref-22), here we will apply the primal-dual method directly to the original problem in order to explore its physical properties and solve it in the most efficient way.

After a brief review of the primal-dual logarithmic barrier method we will describe the implementation details in the application of this approach to the ORD. Numerical examples with large scale electric networks are presented and discussed.

## II. The Primal-Dual Algorithm

To apply the primal-dual algorithm, we consider problem (1) in the equivalent form

$$
\begin{aligned}
\min_{z,s_1,s_2}\quad & f(z) - \mu\sum_{j=1}^{n}\left(\log s_{1j} + \log s_{2j}\right) \\
\text{s.t.}\quad & h(z)=0, \\
& z-s_1=\ell, \\
& z+s_2=u, \\
& s_1>0,\quad s_2>0,\quad \mu>0.
\end{aligned}
\qquad (3)
$$

The first-order necessary conditions for (3) are

$$
\begin{aligned}
\nabla f(z)-J(z)^T\lambda-\pi_1-\pi_2 &= 0, \\
h(z) &= 0, \\
z-s_1-\ell &= 0, \\
z+s_2-u &= 0, \\
S_1\pi_1-\mu e &= 0, \\
S_2\pi_2-\mu e &= 0,
\end{aligned}
\qquad (4)
$$

where $\nabla f(z)$ is the gradient of $f$, $J(z)$ is the Jacobian of $h$,
$\lambda\in\mathbb{R}^{m}$ is the multiplier of the equality constraints,
and $\pi_1,\pi_2\in\mathbb{R}^{n}$ are the multipliers associated with the
lower and upper bounds. Here, $e=(1,\ldots,1)^T$, and $S_1$ and $S_2$ are
diagonal matrices with diagonal entries $s_{1j}$ and $s_{2j}$, respectively.

At each iteration, the primal and dual variables are kept strictly interior:

$$
s_1>0,\qquad s_2>0,\qquad \pi_1>0,\qquad \pi_2>0.
\qquad (5)
$$

The linearized Newton system is formed for the direction
$\left(\Delta z,\Delta s_1,\Delta s_2,\Delta\lambda,\Delta\pi_1,\Delta\pi_2\right)$.
Writing

$$
\begin{aligned}
t &= \nabla f(z)-J(z)^T\lambda-\pi_1-\pi_2, \\
v_1 &= \mu e-S_1\pi_1, \\
v_2 &= \mu e-S_2\pi_2, \\
W(z,\lambda) &= \nabla^2 f(z)-\sum_{i=1}^{m}\lambda_i\nabla^2h_i(z),
\end{aligned}
$$

and defining $\Pi_1=\operatorname{diag}(\pi_1)$ and
$\Pi_2=\operatorname{diag}(\pi_2)$, elimination of the slack and multiplier
directions gives the reduced system

$$
\left[
W(z,\lambda)+S_1^{-1}\Pi_1+S_2^{-1}\Pi_2\right]\Delta z
-J(z)^T\Delta\lambda = -t+S_1^{-1}v_1-S_2^{-1}v_2,
$$

$$
J(z)\Delta z=-h(z).
\qquad (15)
$$

The remaining directions are recovered from

$$
\begin{aligned}
\Delta s_1 &= \Delta z, & \Delta s_2 &= -\Delta z, \\
S_1\Delta\pi_1 &= v_1-\Pi_1\Delta s_1, &
S_2\Delta\pi_2 &= v_2-\Pi_2\Delta s_2.
\end{aligned}
\qquad (18)-(21)
$$

The primal and dual step lengths are chosen independently. With a safety factor
$d=0.9995$, the update has the form

$$
\begin{aligned}
z &\leftarrow z+\alpha_p\Delta z, &
 s_i &\leftarrow s_i+\alpha_p\Delta s_i, \\
\lambda &\leftarrow\lambda+\alpha_d\Delta\lambda, &
 \pi_i &\leftarrow\pi_i+\alpha_d\Delta\pi_i,
\end{aligned}
\qquad i\in\{1,2\}.
\qquad (24)-(29)
$$

A critical point in the primal-dual algorithm is the choice of the barrier
parameter $\mu$. In linear programming it is usually estimated from the
predicted decrease of the duality gap.
## III. Network Modeling

ORD is a particular case of OPF in which active controls are fixed. Control optimization are only related to reactive power - voltage level for generators, synchronous condensers and static VAr systems; taps; switchable banks. The objective are one of the following correction of the voltage profile of the network, minimization of active power losses for a given set of generation injections, maximization of reactive reserve, minimization of reactive injection costs, etc. In these problems it is assumed that active controls were chosen in such a way that there are no circuit overloads or any other active power flow related problem. If there exist, some kind of active power redispatch should be previously considered. ORD can be considered for on-line applications but our primary research interest is to consider the application of interior point methods to ORD in our VAr planning activities.

The equality constraints of problem (1) corresponds to an AC power flow model and in the numerical examples described in this paper the inequality constraints are just bounds in the variables - there are no functional inequality constraints. Furthermore all controls are assumed to be continuous. This can be a serious limitation such as for switchable banks but the present state-of-art of optimization algorithms does not allow a large number of discrete variables to be fully optimized in a large scale nonlinear programming problem. For some specific applications some kind of pt-optimization strategy may be necessary.

To illustrate the application of the primal-dual algorithm, two types of ORD
will be considered. The first is the optimal reactive allocation problem:

$$
\begin{aligned}
\min\quad & \sum_{k=1}^{N}\left(c_{1k}s_{1k}+c_{2k}s_{2k}\right) \\
\text{s.t.}\quad & P_k^{\mathrm{gen}}-P_k^{\mathrm{load}}=P_k(V,\theta), \\
& Q_k^{\mathrm{gen}}-Q_k^{\mathrm{load}}=Q_k(V,\theta), \\
& \ell\le z\le u, \\
& P_k^{\mathrm{gen}}=P_k^0\quad (k=1,\ldots,N,\ k\ne k_g).
\end{aligned}
\qquad (41)
$$

Here, $t_j$ is the tap ratio of the $j$th in-phase controllable transformer,
$V_k$ is the voltage magnitude at bus $k$, $\theta_k$ is its voltage angle,
and $N$ is the number of buses. The variables $s_{1k}$ and $s_{2k}$ represent
capacitive and inductive reactive injections, with corresponding costs
$c_{1k}$ and $c_{2k}$.
This problem is considered in the VAr-planning context, and its objective is to
minimize the reactive-power injection cost required to keep the system feasible.
It can be viewed as a stand-alone problem or as a subproblem in a Benders
decomposition of the reactive-power expansion problem (see [28](#ref-28)).

The second problem has the same constraints and uses a composite objective:

$$
\min\quad \sum_{k=1}^{N}\left(c_{1k}s_{1k}+c_{2k}s_{2k}\right)
    +W\,\operatorname{loss}(V,\theta,t),
\qquad (42)
$$

where $\operatorname{loss}(V,\theta,t)$ is the active-power loss and $W$ is
the trade-off factor between reactive-injection cost and active-power loss.
Here we could just consider loss minimization but the purpose was to observe the performance of the algorithm in handling the two conflicting objective. The author is aware that unless proper weights are specified the algorithm may reach a solution that would be both unsatisfactory in loss minimization and reactive injections costs.

In the formulation of the above problems only one slack bus was specified and the result of the optimization may depend on the choice of that bus. However this is a common practice for VAr

planning in the industry, also the formulation can be extended to consider more than one slack bus.

Note that for some specific condition problems (41) or (42) may be infeasible. Infeasibility detection is an important issue in on-line applications. As all variables are kept within bounds in the successive iterations of the primal-dual algorithm, infeasibility here would be translated in terms of impossibility in closing active or reactive power balance equations in some buses. Besides having to make specific analysis for each specific case, at the present moment we do not have any automatic procedure to deal with this problem.

Another issue is contingency handling. Contingency is an important issue for VAr planning. At the present moment a Benders decomposition scheme together with the primal-dual algorithm is being implemented at CEPEL to solve the problem of finding settings for the reactive control variables in such a way to optimize a given objective function in the base case configuration and at the same time be feasible for the contingencies with the constraint that only some of these controls (user specified) may change from the base case to contingency. In the resolution of this problem each contingency subproblem solved with the primal-dual algorithm will send a linear constraint (Benders cut) to the base case subproblem which will also be solved with the primal-dual algorithm.

## IV. Implementation

Most of the work in the primal-dual algorithm is in solving system (17). We
use an approach related to the decoupled Newton optimal-power-flow method of
Sun et al. [8](#ref-8). The Newton matrix is approximated by a two-block
structure:

$$
\begin{bmatrix}
W_{11} & W_{12} \\
W_{21} & W_{22}
\end{bmatrix}\begin{bmatrix}\Delta z_1\\\Delta z_2\end{bmatrix}
=\begin{bmatrix}r_1\\r_2\end{bmatrix}.
\qquad (43)
$$

The light border contains tap, reactive-generation, and bank-control variables.
The heavy border has a $2\times2$ block structure, with each diagonal block
corresponding to the voltage magnitude and reactive multiplier of one bus. The
structure also accommodates non-network constraints such as Benders cuts,
functional constraints, and contingency constraints. The system is solved by
eliminating the off-diagonal elements of the light border, then factorizing and
solving the heavy-border system.

With respect to initialization, the only requirements are that the variables are interior to the bound constraints. The network balance equations or any other equality constraints (note that an inequality constraint together with its slack variable becomes an equality constraint) are not required to be satisfied at the starting point.' In this context the algorithm is not a truly interior point method as the iterates are interior only with respect to the bound constraints. If for a given starting point some of its component are not interior to the bound constraints this component is modified to become within a certain tolerance of the bound constraint. The numerical experiments made so far have shown that this strategy is very effective and the algorithm is quite robust with respect to starting points.

Another issue is ill-conditionings when the iterates are close to the optimal solution. Let k(p) the Hessian of the barrier function condition number. It can be proved that k(p) goes to infinity as p goes to zero if the number of active constraints t is such that 0 < t e n. This fact may bring numerical difficulties to the interior point algorithm and there are some proposed remedies to deal with it (see [30](#ref-30), [31](#ref-31)). Up to this moment we did not encounter any of these ill-conditioning problems even with the composite objective function or with hot starting. However we do not rule out the possibility that in the near future we have to deal with them.

## V. Numerical Results

The blocks $W_{11}$ and $W_{22}$ correspond to active- and reactive-power
variables, respectively. The Jacobian blocks $J_{11}$ and $J_{22}$ correspond
to the active- and reactive-power balance equations. The approximation used for
the active-power block is

$$
J_{11}=B'V,
\qquad
B'_{ij}=\begin{cases}
-x_{ij}^{-1}, & i\ne j,\\
\displaystyle\sum_{k\in\mathcal{N}_i}x_{ik}^{-1}, & i=j,
\end{cases}
\qquad (45)
$$

where $B'$ is square, $V$ is diagonal, and $\mathcal{N}_i$ is the set of buses
connected to bus $i$.

The application of the primal-dual barrier algorithm will be illustrated in two large scale electric networks. The first one is the Brazilian SUL/SUDESTE generation/transmission system for the year of 1995, with severe voltage problems and the following characteristics:

1832 buses 2647 circuits 210 LTC controls 164 KV controls.

The second is a network derived from a North American generation/transmission system with the following characteristics: 3467 buses 6412 circuits 874 LTC controls 454 KV controls.

The ORD is sensitive to the bus voltage limits. Here these limits were defined based on the voltages specified in the input data. Taking them as nominal, a fixed percentage in deviation of magnitude was allowed.

Here, $V$ is a diagonal matrix whose diagonal elements are $v_i$, $i=1,
\ldots,N$, and $\mathcal{N}_i$ is the set of buses connected to bus $i$.

Further, submatrix $W_{11}$ is also neglected.

> Note that with the above approximations, system (17) can be solved in three
> steps: first with respect to the active-power variables, then with respect to
> the active-power multipliers, and finally with respect to the reactive-power
> variables and multipliers. In the actual implementation, all quantities are
> updated after each system is solved. The solution for the active-power
> variables corresponds to the active iteration of the fast-decoupled
> load-flow algorithm (see [29](#ref-29)).

No approximations are made to submatrix (44).

The initial and minimum values of the barrier parameter $\mu$ were taken to be
$5.0$ and $5.0\times 10^{-4}$, respectively, and the parameter $p$ (see
Eq. (40)) was set to $10$. Sometimes convergence can be improved by setting
the barrier parameter for reactive-generation and injection variables to a
fraction of the corresponding value for voltage-magnitude and tap variables.
Unless otherwise specified, this fraction was taken to be $1/10$ in the
numerical results below.

For the termination criteria, several conditions should be satisfied:

- $\mu < 5.1\times 10^{-4}$.
- Active/reactive power-balance equation mismatches should be less than
    $1\,\mathrm{MW}/1\,\mathrm{MVAr}$.
- $\lVert t\rVert < 10^{-4}$, where $t$ is the Lagrangian gradient (see
    Eq. (4)).

The normalized Euclidean norm used for residual vectors is

$$
\lVert v\rVert = \frac{1}{n}\left(\sum_{i=1}^{n}v_i^2\right)^{1/2},
\qquad v\in\mathbb{R}^{n}.
$$

The computational work described below was performed on a 386 computer with
a 25 MHz microprocessor using single-precision arithmetic. The first
experiment consisted of optimal reactive allocation for the Brazilian
SUL/SUDESTE network, with unit reactive-injection costs at all buses and a 5%
voltage-magnitude deviation. The algorithm converged in 45 iterations, with a
total of 834.0 MVAr of reactive injections distributed over 17 buses (12 with
capacitive injections and 5 with inductive injections) and total active-power
losses of 1781.3 MW.

Figure 1 shows the evolution of the maximum active- and reactive-power
mismatches. The initial mismatches were high, at 35,210 MW and 43,667 MVAr,
and the reactive-power mismatches decreased more slowly than the active-power
mismatches. This probably reflects the voltage conditions in the network. The
inset shows the mismatches from iteration 35 onward on a different scale.

Figure 2 shows the evolution of the objective function. It initially increased
to a maximum of 5163.69 MVAr at iteration 19. At that point, the barrier
parameter $\mu$ was still equal to 1.2. It then decreased more rapidly and
reached its minimum value of $5.0\times10^{-4}$ at iteration 35. Attempts to
make $\mu$ decrease faster by increasing $p$ (for example, setting $p=100$) did
not reduce the total number of iterations. CPU time for this run was 206.4
seconds.

In the second experiment, the same network was considered with a 10% voltage-
magnitude deviation to observe the sensitivity of the optimal reactive
injection to the voltage tolerance. The algorithm converged in 40 iterations.
The total reactive allocation decreased from 834.0 MVAr to 3.47 MVAr, and
total active-power losses were 1704.2 MW. Figures 3 and 4 show the evolution
of the maximum active/reactive-power mismatches and the objective function,
respectively. The insets show the corresponding quantities on a different
scale from iteration 28 onward. CPU time for this run was 182.8 seconds.

The third experiment used the composite objective function (42) to minimize
active-power losses and injection costs in the same network. The trade-off
factor was set to one, and a 10% voltage-magnitude deviation was specified as
in the preceding case. The algorithm converged in 40 iterations. Reactive
allocation increased from 3.64 MVAr to 8.24 MVAr, while total active-power
losses dropped from 1704.2 MW to 1619.3 MW, a 5% reduction. Figure 5 shows the
evolution of active-power losses. CPU time for this run was 398.9 seconds.



We next consider the larger network, with 3467 buses. For the reactive
allocation problem, unit reactive-injection costs were used at all buses and a
5% voltage-magnitude deviation was allowed. The algorithm converged in 53
iterations, with a total reactive allocation of 86.18 MVAr distributed over
eight buses (6 with capacitive injections and 2 with inductive injections).
Total active-power losses were 2567.2 MW. Figures 6 and 7 show the maximum
active/reactive-power mismatches and the objective function, respectively. The
barrier parameter decreased more rapidly than in the preceding cases: it was
$4.1\times10^{-3}$ at iteration 10 and reached its specified minimum value of
$5.0\times10^{-4}$ at iteration 17. The algorithm nevertheless required a
relatively large number of iterations to attain feasibility and optimality.
CPU time for this run was 595.34 seconds.

As a test of robustness with respect to the starting point, the same
optimization was started from a flat initial point. The algorithm converged in
57 iterations, with a total reactive allocation of 81.19 MVAr distributed over
eight buses. This differed by only 0.01 MVAr at two buses from the preceding
run.

The next run used the composite objective function (42), with a trade-off
factor of one and the same 5% voltage-magnitude deviation. The same barrier
parameter was used for the reactive-generation/injection variables and the
voltage-magnitude/tap variables. The algorithm converged in 29 iterations. The
reactive allocation increased from 86.18 MVAr to 111.87 MVAr, while active-
power losses dropped from 2567.2 MW to 2414.9 MW, a 6% reduction. Figure 8
shows the evolution of active-power losses.

As a final robustness test, a restarting procedure was applied to the larger
network with the reactive allocation problem. Five contingencies were
considered, using the optimal primal and dual variables of the base-case
solution as the starting point. Contingencies 1 through 3 converged in 6
iterations, contingency 4 in 5 iterations, and contingency 5 in 14
iterations. The total injection for the last contingency was 122.08 MVAr.
Starting from the input data with an initial barrier parameter of 5.0, the
algorithm converged for this contingency in 31 iterations, with an optimal
objective value of 122.59 MVAr, a difference of 0.51 MVAr. This result shows
that hot starting may be an attractive strategy for applying the primal-dual
algorithm to ORD. It also highlights the importance of the dual variables for
hot starting compared with the original logarithmic-barrier method.

The numerical experiments show that the number of iterations is not very
sensitive to the network size or the number of control variables. Each
iteration, however, requires the computation and factorization of a Newton-type
matrix.

Another important feature is robustness. One of the most difficult problems in
Newton optimal power flow is identifying the active set, that is, the set of
constraints active at the optimum. The barrier method avoids trial iterations
for active-set identification because the slacks of constraints that become
active naturally approach their bounds. Monticelli and Liu [32](#ref-32) also
described singularity or near-singularity problems inherent in Newton optimal
power flow and proposed a movement-penalty strategy. None of these numerical
problems were observed in the experiments, including hot starts. The barrier
terms contribute to the diagonal of the Hessian matrix (see Eq. (15)), helping
to maintain positive definiteness without auxiliary penalty functions.

Overall, the primal-dual algorithm was effective for solving optimal reactive
allocation and loss-reduction problems in large-scale, ill-conditioned
networks.

## VI. Conclusions

In this paper we considered the application of an interior point algorithm based on the pnmal-dual logarithmic barrier method to ORD which is a large scale nonconvex nonlinear programming problem with nonlinear constraints.

Our numerical experiments (in 1832 bus and 3467 bus networks) have shown that it can be very attractive to some optimal

power flow applications in large scale electric networks. Its main features are:

- Number of iterations is not very sensitive to network size or number of control variables,

- - Numerical robustness,

- Hot starting capability,

- No active set identification difficulties,

- Effectiveness in dealing with optimal reactive allocation and loss reduction problems in large scale and ill-conditioned networks.

## VII. Acknowledgements

The author is grateful to Luiz M. Thome and the ANAREDE group of CEPEL for providing a general framework for research and developnient of new algorithms in power systems optimization. 'hanks go to Clovis C. Gonzaga, Ricardo Arantes of COPPE and Paulo A. Machado, Luiz A. Cordeiro of CEPEL for helpful discussions in interior point algorithms and their implementations to power systems. Thanks also go to Mario V. F. Pereira for helpful comments in the original manuscript and Maria C. A. Lima for her help in the composition of this paper.

## VIII. References

<a id="ref-1"></a>
1. J. Carpentier, "Contribution a l'etude du dispatching economique," *Bulletin de la Societe Francaise des Electriciens*, series 8, vol. 3, 1962.

<a id="ref-2"></a>
2. H. W. Dommel and W. F. Tinney, "Optimal power flow solutions," *IEEE Transactions on Power Apparatus and Systems*, vol. PAS-87, 1968.

<a id="ref-3"></a>
3. J. Abadie and J. Carpentier, "Generalization of the Wolfe gradient method to the case of nonlinear constraints," in *Optimization*, Academic Press, 1969.

<a id="ref-4"></a>
4. J. Carpentier, "Differential injections methods: A general method for secure and optimal load flows," IEEE PICA Conference Proceedings, Minneapolis, 1973.

<a id="ref-5"></a>
5. B. A. Murtagh and M. A. Saunders, "A projected Lagrangian algorithm and its implementation for sparse nonlinear constraints," *Mathematical Programming Study*, vol. 16, 1982.

<a id="ref-6"></a>
6. M. C. Biggs and M. A. Laughton, "Optimal electric power scheduling: A large nonlinear programming test problem solved by recursive quadratic programming," *Mathematical Programming*, vol. 13, 1977.

<a id="ref-7"></a>
7. R. C. Burchett, H. H. Happ, and D. R. Vierath, "Quadratically convergent optimal power flow," *IEEE Transactions on Power Apparatus and Systems*, vol. 103, 1984.

<a id="ref-8"></a>
8. D. J. Sun, B. Ashley, B. Brewer, A. Hughes, and W. F. Tinney, "Optimal power flow by Newton approach," *IEEE Transactions on Power Apparatus and Systems*, vol. 103, 1984.

<a id="ref-9"></a>
9. O. Alsac, J. Bright, M. Prais, and B. Stott, "Further developments in LP-based optimal power flow," *IEEE Transactions on Power Apparatus and Systems*, vol. 5, 1990.

<a id="ref-10"></a>
10. S. Granville, M. C. Lima, L. C. Lima, and S. Prado, "Planvar: An optimization software for VAr sources planning," paper presented at the 14th Symposium in Mathematical Programming, Amsterdam, 1991.

<a id="ref-11"></a>
11. N. Karmarkar, "A new polynomial time algorithm for linear programming," *Combinatorica*, vol. 4, 1984.

<a id="ref-12"></a>
12. N. Karmarkar, "Recent developments in new approaches to linear programming," SIAM Conference on Optimization, Houston, TX, 1987.

<a id="ref-13"></a>
13. C. L. Monma and A. J. Morton, "Computational experience with dual affine variant of Karmarkar's method for linear programming," *Operations Research Letters*, vol. 6, no. 6, 1987.

<a id="ref-14"></a>
14. I. Adler, N. Karmarkar, M. G. C. Resende, and G. Veiga, "An implementation of Karmarkar's algorithm for linear programming," Report ORC-86-8, University of California, Berkeley, 1986.

<a id="ref-15"></a>
15. P. E. Gill, W. Murray, and M. A. Saunders, "Interior-point methods for linear programming: A challenge to the simplex method," Technical Report SOL 88-14, Stanford University, 1988.

<a id="ref-16"></a>
16. K. A. McShane, C. L. Monma, and D. Shanno, "An implementation of primal-dual interior point method for linear programming," *ORSA Journal on Computing*, vol. 1, 1989.

<a id="ref-17"></a>
17. S. Mehrotra, "On the implementation of a primal-dual interior point method," Technical Report 90-03, Northwestern University, 1990.

<a id="ref-18"></a>
18. I. J. Lustig, R. E. Marsten, and D. F. Shanno, "Computational experience with a primal-dual interior point method for linear programming," *Linear Algebra and its Applications*, vol. 152, 1991.

<a id="ref-19"></a>
19. C. C. Gonzaga, "Path following methods for linear programming," *SIAM Review*, to be published.

<a id="ref-20"></a>
20. C. G. Han, P. M. Pardalos, and Y. Ye, "Solving some engineering problems using an interior point algorithm," manuscript, Pennsylvania State University, 1991.

<a id="ref-21"></a>
21. R. J. Vanderbei, T. J. Carpenter, J. J. Carpenter, I. J. Lustig, J. M. Mulvey, and D. F. Shanno, "Symmetric indefinite systems for interior-point methods," Report SOR-91-7, Princeton University, 1991.

<a id="ref-22"></a>
22. C. J. Lustig, J. M. Mulvey, and D. F. Shanno, "A primal-dual interior point method for convex nonlinear programs," RUTCOR Research Report, Rutgers University, 1990.

<a id="ref-23"></a>
23. K. Ponnambalam, V. H. Quintana, and A. Vannelli, "A fast algorithm for power system optimization problems using an interior point algorithm," 17th PICA, Baltimore, 1991.

<a id="ref-24"></a>
24. R. C. Burchett and I. S. Grant, "Application of a new high-speed nonlinear optimal power flow," Power Technology, Inc., issue 58, 1989.

<a id="ref-25"></a>
25. K. A. Clements, "Interior-point optimization methods," in *Advanced Optimization Techniques*, 1991 PICA Tutorial.

<a id="ref-26"></a>
26. R. D. C. Monteiro and I. Adler, "Interior path following primal-dual algorithm. Part I: Linear programming," *Mathematical Programming*, vol. 44, 1989.

<a id="ref-27"></a>
27. R. D. C. Monteiro and I. Adler, "Interior path following primal-dual algorithm. Part II: Convex quadratic programming," *Mathematical Programming*, vol. 44, 1989.

<a id="ref-28"></a>
28. S. Granville, M. V. F. Pereira, and A. Monticelli, "An integrated methodology for VAr sources planning," *IEEE Transactions on Power Apparatus and Systems*, vol. 3, 1988.

<a id="ref-29"></a>
29. B. Stott and O. Alsac, "Fast decoupled load flow," *IEEE Transactions on Power Apparatus and Systems*, vol. 93, 1974.

<a id="ref-30"></a>
30. H. W. Wright, "Numerical issues in interior methods for nonlinear programming," 14th Symposium in Mathematical Programming, Amsterdam, 1991.

<a id="ref-31"></a>
31. P. E. Gill, W. Murray, D. Ponceleon, and M. A. Saunders, "Solving KKT systems in barrier methods for linear and quadratic programming," Technical Report SOL 91-7, Stanford University, 1991.

<a id="ref-32"></a>
32. A. Monticelli and W. E. Liu, "Adaptive movement penalty method for the Newton optimal power flow," paper 90 WM 251-9 PWRS, IEEE/PES Winter Meeting, Atlanta, 1990.

<a id="ref-33"></a>
33. M. S. Bazarra and C. M. Shetty, *Nonlinear Programming: Theory and Algorithms*, John Wiley & Sons, 1970.

<a id="ref-34"></a>
34. M. H. Wright and M. Murray, "Line search procedures for the logarithm barrier function," AT&T Bell Laboratories, Numerical Analysis Manuscript 92-01, 1992.
## Biography

Sergio Granville received the B.Sc. degree in Mathematics in 1971 and the M.Sc. degree in Applied Mathematics in 1973, both from the Pontificia Universidade Catolica do Rio de Janeiro, and the Ph.D. degree in Operations Research in 1978 from Stanford University. From 1984 to 1985 he was a Visiting Scholar at the Department of Operations Research at Stanford University. Since 1986, he has been a Senior Researcher at CEPEL. His research interests include transmission planning, reactive power planning, optimal power flow, and applications of optimization techniques to power system planning and operation.
Discussion

possible violation of limits. What is the author’s opinion on this question?

Xing Yong H. Chao and Ram611 Nadira (Power Technologies, Inc., Schenectady. NY): The author is to be commended for applying the interior point method to the nonlinear optimization problems in power systems. The efficiency of this method is favorable for large size systems, and the selected primal-dual algorithm has been considered as the best interior point algorithm. From the application point of view as oriented by this paper, clarification of the following comments is appreciated:

- One of the very practical issues in OPF is how to handle the discrete controls, such as the transformer taps and switchable shunts. Is there good way of doing this, especially associated with the Interior Point method?

- What happen if a case is infeasible? Is there an embedded strategy in the method to suggest the best solution?

- Eqs. (38) and (40) should have residues from both primal and dual spaces incorporated because these residues indicate the primal and dual infeasibilities, respectively. This is especially true at the start of the algorithm. U~ealistic estimates of the duality gap and calculation of the barrier parameter may result in slower implementation of the method.

Would the author comment on why the objective function becomes non-increasing only after a certain number of initial iterations. There are many arguments for applying an interior point method t o a non-linear problem directly as done by the author (instead of applying it to a sequence of linear programs). However, one possible advantage (besides others) in solving a sequence of linear programs is the ability to combine the simplex method with an interior point method [A](#ref-a). This can sometimes be useful for the hot (warm) start feature.

The problem described in this paper is similar to the one solved for incorporating inequality constraints in the state estimation problem [A2](#ref-a2). However, unlike [A2](#ref-a2), this paper (correctly) uses different primal and dual step sizes to preserve primal and dual feasibility at every step. It also notes in eq.(22) and eq.(23) that the ratio test for feasibility can yield a step size larger than the Newton step in which case the Newton step is chosen.

Another issue common to this paper and [A2](#ref-a2) is the question of initialization. Inequality constraints involving bounds on variables, such as limits on voltage magnitudes are not difficult to handle (eq.(3.1) and eq.(3.2) of the paper). The case of functional inequality constraints is more interesting. Let these constraints be represented

as

4 2 )_ L U , 9 ( 2 ) L _1_ (1)

- It has been noticed that the barrier calculated as in Eq._ (39) varies with different cases and starting points. Its magnitude can be in thousands or in decimals. Since this parameter controls the step length, the speed of the solution is directly affected by the user’s selection of it (as indicated in the paper). In addition, the stopping criterion of p < 5.1 x may result in a premature stop of the algorithm. It seems smaller values should be used because for some infeasible problems, before the algorithm blows up, the duality gap may get within this tolerance. Has such a phenomenon been observed ever?

- Even in LP, the tracing of central trajectory and varying of the duality gap are not the same concept. As a matter of fact, the later has a dominant effect on the number of iterations. It can take quite a few initial steps for the algorithm to narrow the gap, zem out the residues in both primal and dual spaces, and decrease the barrier parameter. The reported test results have shown probably such a phenomenon since Eq. (40) is used. Have different initialization been tried to minimize the iterations of the first stage of this algorithm? If so, is there any scaling scheme involved?

By introducing additional variables s1 and s2, they can be written as



There is more than one way of initializing the resulting problem. A modified problem that minimizes the sum of infeasibilities in the inequality constraints can be solved [A3](#ref-a3). This is similar t o the phase 1 problem in linear programming when the simplex method is used. This phase 1 problem is solved until all inequalities become feasible. The step size ensures that feasible inequalities remain feasible. Another somewhat ad-hoc phase 1 problem solved by this discusser used a modified problem with equalities

s(x) = b_ (4)

where b is chosen such that ( l < b < U). However, skewed and incorrect limits can be difficult to handle. The technique suggested by the author chooses feasible s1 and s2 and satisfies the corresponding non-linear equality constraints only at convergence (rather than at every step). This seems, at least t o this discusser, a very attractive method of initialization. The author’s comments on his experience with different initialization techniques would be very useful.

### Discussion

#### H. Singh (University of Wisconsin-Madison) The author is t o be complimented for his impressive work which was done on a P C using single precision arithmetic. This is somewhat intriguing as the method used by the author involves inherent ill-conditioning of the Hessian when the barrier parameter goes t o zero and only a subset of the inequality constraints are binding. Would the author provide some information of how many inequality constraints were binding in the solution.

Infeasibility in the problem is characterized by the nonconvergence of the non-linear equality constraints. The underlying cause for this is the specification of overly strict limits in the form of inequality constraints. In practice, it may be more useful to have a solution that satisfies the non-linear equality constraints with a

<a id="ref-a"></a>
- [A](#ref-a) Bixby, R.E., J.W. Gregory, I.J. Lustig, R.E. Marsten and D.F. Shanno, “Very Large Scale Programming: A Case Study in Interior Point and Simplex Methods,” Operations Research, Vol. 40, NO. 5, Sept.-Oct 1992.

<a id="ref-a2"></a>
- [A2](#ref-a2) Clements, K.A., P.W. Davis and K.D. Frey, “Treatment of Inequality Constraints in Power System State Estimation,” ZEEE Winter Power Meeting, Paper 91-WM 235-2 PWRS, New York, Feb 1991.

<a id="ref-a3"></a>
- [A3](#ref-a3) Fiacco, A. and G. McCormick, “Nonlinear Programming: Sequential Unconstrained Minimization Techni,ques,” John Wiley and Sons, New York, 1968 (re-printed by SIAM).

Manuscript received February 23. 1993.

YU-CHI W U and ATIF S. DEBS (School of Electrical Engineering, Georgia Institute of Technology, Atlanta, GA): The author is to be commended for using a primal-dual interior point method with decoupling mechanism to solve the optimal reactive dispatch problem. From discussers’ point of view, there are 4 points to be _addressed:_

(i) Since in the algorithm the so-called duality gap (the difference between the primal and dual objectives) is not monitored in convergence checking, how will the author justify the optimality of the solution, i.e., what is the degree of the accuracy of the final solution? For the nonlinear optimization problem (2) considered in the paper, the duality gap can be expressed as

and the complementary slackness conditions

$S_1\pi_1 e = \mu e$ and $S_2\pi_2 e = \mu e$

have to be satisfied for a sufficient small p. If J . L . = ~ O ~ ~ is chosen as a convergence criterion, then when the dimension of SI (or s2), n, is large the complementary gap 6s’ + IC$% = 2np will become large too. Consequently, the duality gap is not negligible. In this case, the convergence criteria used in author’s algorithm will not be sufficient enough. How will the author deal with this situation?

(ii) Has the author thought about using the relative duality gap as one of the convergence criteria? And if the relative duality gap is chosen, how will the performance of the algorithm change due to different settings of relative duality gap threshold?

(iii) Based on discussers’ understanding, in order to have better performance of interior point methods, double precision and possibly quadruple arithmetic is suggested. Could the author comment on the effect to the solution if double precision is used?

(iv) Different step sizes are used in primal and dual spaces to update the variables in the algorithm. From the mathematical point of view, the primal variables also appear in the dual constraints, Eq. (9), and only one step size can be chosen to comply with the Newton’s direction in the primal-dual space unless there is no decoupling of variables in the dual constraints. Could the author comment on the effect if only one step size is chosen for both primal and dual variables?

method to optimal reactive dispatch. We would appreciate his comments on the following points:

- The implementation of the interior point method proposed in the paper performs successfully in the solution of the ORD. However, in order to have a better appraisal of its performance, a comparison with standard optimization solvers could provide a clearer perspective of the advantages of the proposed technique. Has the author compared his results with other optimization solvers such as MINOS in the solution of the ORD?

- As stated by the author, interior point methods perform better than simplex in a wide range of problems when the number of variables and constraints is large. However, in practical applications, even for small systems, interior points methods can obtain faster results than simplex. This is particularly true for the dual affine version of interior point methods, where even for systems with small number of variables (less than 1001, its performs better than MINOS [A](#ref-a). We have used the dual affine version to solve the security constrained economic dispatch problem [B](#ref-b). Our results coincide with those exhibit in the paper, i.e., we have found that as the size of the problem increases the total number of iterations does not change significantly; and we also noticed that the number of iterations of the algorithm is not very sensitive to the size of the network. In addition, we found that the overall execution time grow at a slower rate in the interior point method than in the simplex method for the IEEE 30 buses and 118 buses systems.

- In reference [C](#ref-c) a problem near to the worst case for simplex was presented. The solution time is proportional to 2”-’ ( n being the dimension of the problem), as opposed to the original interior point method proposed by Karmarkar which is proportional to n3.5 [11](#ref-11). Thus, for a problem of this type, we may have few variables (less than ten) together with a larger amount of constraints and the dual affine will perform better than simplex. According to our experience with the dual affine method [D](#ref-d), as the number of constraints is increased, simplex method becomes slower than the dual affine even for problems with a small number of variables.

Finally, we congratulate again the authors for his work in this exciting area of power system optimization.

### Discussion References
> Manuscript received March 2, 1993.

L. Vargas and V. H. Quintana (University of Waterloo, Waterloo, Ontario, Canada): The author is to be commended for his interesting application of an interior Doint

<a id="ref-a"></a>
- [A](#ref-a) Adler, I., Resende, M., Veiga, G. and Karmarkar, N., “An implementation of Karmarkar’s algorithm for linear programming,” Mathematical Programming 44, pp. 297-335, 1989.

<a id="ref-b"></a>
- [B](#ref-b) Vargas, L., Quintana, V. H., and Vannelli, A., “A Tutorial Description of an Interior Point Method and its Applications to Security-Constrained Economic Dispatch,” IEEE PES 1992 Summer Meeting, Seattle. Washineton. Julv 1992.

<a id="ref-c"></a>
- [C](#ref-c) Klee, V. and Minty, G. J., “How Good is the Simplex Algorithm?”, in Inequalities III, Academic Press, New York, N.Y., 1972, pp. 159-175.

<a id="ref-d"></a>
- [D](#ref-d) Vannelli, A., Quintana, V. H., and Vargas, L., “Interior Point Optimization Methods: Theory, Implementations and Engineering Applications,” Canadian Journal on Electrical and Computer Engineering,_ Vol. 17, NO. 2, pp. 84-94, 1992.

#### Manuscript received March 9, 1993.

Sergio Granville. We would like to thank the discussers for the important aspects raised from the paper and to give us an opportunity to further clarify it. There are a large number of points which I will try to respond to in the following.

#### Chao And Nadira

- Discrete controls. Discrete controls are an important aspect for VAr planning like transfonner taps and switchable banks. Unfortunately the present state-of-art optimization algorithm does not allow a large number of integer variables to be fully optimized in a large scale nonlinear programming problem. Also the application of interior point methods to large scale combinatorial problems is still very limited. Therefore in real application some kind of rounding off procedure is necessary. It should be observed that in practice transformer tap discretization seems to present no difficulties as with respect to switchable reactor/capacitor banks, due to the size of the steps.

- Infeasibility. As all variables are within bounds in the successive iterations of the primal-dual algorithm presented in the paper, infeasibility would be translated in terms of impossibility in closing active or reactive power balance equations in some buses. However, from the absolute value of the dual variables associated to the innequality constraints or bounds it is possible to detect which one (or ones) of these constraints is causing the infeasibility. For instance, a test was made with the Brazilian 1832 buses network by specifying a voltage range of 0.95-1.05 for all buses. It was observed that by the 20* iteration that the reactive power balance equation maximum mismatch was not decreasing and was still greater than the prespecified tolerance. The value of the dual variable associated to the lower bound of the voltage level variable in bus 40 was 63.5 which is high in relation to other dual variables and unit cost function. Then the lower bound for that variable was reduced to 0.9 and the algorithm converged in 5 more iterations.

- Residues at eqs. (38) and (40). Firstly It should be noted that several strategies for reducing the barrier parameter were tried and the one corresponding to formula (40) showed the best numerical performance. Note that as ORD is a nonlinear nonconvex programming problem we do not have for it the nice duality properties of linear programming (in particular that the duality gap should be zero at the optimal solution). Then the author is aware that there is no theoretical basis (at least for the moment) for using eq. (40) for updating the barrier parameter. The development shown in the text for linear programming was just a motivation for it. Note that

   - even for linear programming it is not easy to define the duality gap at infeasible points.

4. Initial barrier parameter. Note that the initial barrier parameter is specified by the user - formula (40) is only used to determine it after the first iteration. The choice for the numerical values of the initial and f i ~ barrier parameter l (5.0 and 5.0~10‘) was quite satisfactory _so_ far for the ORD problems taken from our VAr planning activities at CEPEL - attempts to decrease the final barrier parameter did not improve the performance of the method on those problem. Also benchmarks are frequently done with CEPEL‘s VAr planning program. The author is aware that different values should be considered in order applications.

5. Central trajectory. The central trajectory is the path, parametrized by the barrier parameter, defined at each value of the barrier as the solution of the optimization problem corresponding to the composite objective function (original objective plus barrier terms) and original constraints. This path is in linear programming the region with attractive primal-dual properties (see reference [ 191 in the paper) and that is the reason why the primal dual algorithm in linear programming by to follow to it. The duality gap on the other hand approaches zero as the barrier parameter goes to zero. Actually in some cases secondary iterations with fixed barrier are considered to bring iterates close to this path. Here we did not considered these refinements.

#### Wu and Debs

1. Duality gap. Please first refer to item (3) and (4) in answer to Chao and Nadira above. Note that for nonlinear programming the duality gap is defined based on the Lagrangian duality theory (see reference [33](#ref-33) below). Also for linear programming the termination criteria for the primal-dual algorithm is in general based on the relative duality gap (see reference [18](#ref-18) in the paper for instance).

2. Higher precision. The algorithm presented on the paper was also implemented in double precision but no improvements in performance was observed for the ORD test cases considered so far. The author agrees that a general purpose software based on interior point algorithm should be implemented in double precision with a numerically robust line search procedure (see reference [31](#ref-31) in the paper and reference [34](#ref-34) below).

3. Step sizes. Early implementations of primal-dual algorithm for linear programming used the same step size for the primal and dual variables (see reference [16](#ref-16) in the paper for example). Later it was observed that taking different steps in the primal and dual variables leads to fewer iterations (see references [18](#ref-18) and [31](#ref-31) in the paper for instance). Here the attempt to define the same step sizes for the primal and dual variables has indeed degraded the performance of the algorithm on ORD test cases.

1. Ill-conditioning. The author agrees as observed in the paper that ill-conditioning is a major concern in the application of

barrier methods to nonlinear programming if only a reduced subset of the inequality constraints is binding at the optimal solution. For instance problem (41) in the 3467 buses network corresponds to an optimization problem with about 15000 variables, 6900 nonlinear equality constraints and 23500 bound constraints. In the optimal solution only 3915 bound constraints were active (constraints that were within 1 .0x104 from its rhs). The optimal solution corresponding to the composite objective function (problem (42)) considered in the same network network had only 458 active bound constraints. Due to the loss minimization requirement, the voltage level variables were kept higher than in previous case, and the number of active bound constraint was much lower. In this case the number of active inequality constraint was very small as compared to the total number of inequality constraint.

2. Infeasibility. Please refer to item (2) in response to Chao and Nadira.

3. Objective function behavior. In the numerical experiments it has been observed that the objective function only becomes non-increasing when the active and reactive power balance equations mismatches become less than a certain value. This reflects the tradeoff of attaining feasibility and to minimize the objective function. Also the barrier function, by keeping the variables far from the bounds at early iterations of the algorithm, generally makes the objective function higher at these iterations.

4. Sequence of linear programs. Successive linear programming algorithms have many attractive feature for certain class of optimization problem and the possibility for using linear programming interior algorithms together with the Simplex method makes them even more attractive. However from our numerical experience, successive linear programming does not work well in ORD problems taken from VAr planning because voltage problem networks are in general highly nonlinear. On the other hand from the numerical experiments presented in the paper, hot starting can also be used in the context of the primal-dual algorithm.

5. Initialization. We have just implemented at CEPEL a prototype for the full optimal power flow program (with active power rescheduling) based on the primal-dual algorithm. In this case we had to face the issue of initialization of the functional non linear inequality constraints corresponding to line flow limits. At each iteration line flow were computed for each circuit and the one corresponding to the maximum violation (if any) is

incorporated into the matrix. It was observed that the technique suggested in the paper worked quite well here. We have no experience with other type of initialization.

#### Vargas and Quintana

1. Benchmark. We have at CEPEL a VAr planning program which in one of its resolution options solves problem (41) of the paper through an iterative process: Load flow - quadratic program. The constraints of the quadratic program correspond to the linearization of reactive power balance constraints and its objective is the quadratic approximation of the Lagrangian function of the original problem. The quadratic program is solved through the MINOS system. The application of this program to the 3467 buses network took about 5 hours in a VAX 8810 computer, whereas as mentioned in the paper with the primal-dual algorithm it took less than 10 minutes in a AT 386 microcomputer. This result should be taken with caution because this performance was not only due to the primal-dual algorithm itself but the possibility of taking advantage of the network sparsity structure in the implementation of the method and that it is not so easy with MINOS which is a general purpose system.

2. Interior point method for small systems. The author is grateful to this discusser to remind the results with respect to application of the dual affine version of interior point method to small and medium size systems.

Again, we would like to thank the discussers for their interest and thoughtful comments.

#### Acknowledgments

The author is grateful to Maria de Lujh Latorre fdr her work in the implementation of the prototype for the full optimal power flow program.

### Discussion References
33Bazarra, M.S. and Shetty, C.M., Nonlinear Programming: Theow and Algorithms, John Wiley & Sons (1970). 34Murray, M. and Wright, M.H., "Line Search Procedures for the Logarithm Barrier Function". ATtT Bell Laboratories. Numerical Analysis Manuscript 92-01, 1992.

Manuscript received April 2, 1993.
