"""Run the complete 9-bus NTW/DYN stability workflow."""

from pathlib import Path

from o_grid.dynamics import (
    StabilityConfig,
    StabilityStudy,
    plot_stability_result,
)

network_path = Path("tests/data/ntw/9bus.ntw")
dynamic_path = Path("tests/data/dyn/9bus.dyn")
event_path = Path("tests/data/evt/9bus.evt")

# 1) Parse the NTW and DYN inputs.
study = StabilityStudy(
    network_path,
    dynamic_path,
    event_file=event_path,
    contingency=2,
    config=StabilityConfig(
        duration=10.0,
        time_step=0.01,
        fault_factor=0.2,
    ),
)

# 2) Solve the static operating point.
power_flow = study.run_power_flow()
print(f"Power flow converged: {power_flow.result.converged}")

# 3) Initialize the machines and run the transient stability simulation.
result = study.run()
print(f"Stable: {result.stable}")
print(f"Maximum rotor angle: {result.maximum_angle:.3f} rad")
print("Small-signal eigenvalues:")
for eigenvalue in result.eigenvalues:
    print(f"  {eigenvalue.real:+.5f} {eigenvalue.imag:+.5f}j")

# 4) Plot and save the trajectories.
figure = plot_stability_result(result)
figure.savefig("stability_9bus.png", dpi=150)
print("Saved stability_9bus.png")
