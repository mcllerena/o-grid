"""Python bridge for the Clarabel.jl conic solver."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ClarabelResult:
    """Result returned by Clarabel for a conic program."""

    status: str
    x: list[float]
    z: list[float]
    s: list[float]
    objective: float | None
    iterations: int
    solve_time: float | None


class ClarabelBridge:
    """Solve sparse QP/SOCP/SDP data through a Julia Clarabel environment."""

    def __init__(
        self,
        clarabel_project: str | os.PathLike[str] | None = None,
        *,
        julia_executable: str = "julia",
    ) -> None:
        project = clarabel_project or self.bundled_project()
        self.clarabel_project = Path(project).resolve()
        self.julia_executable = julia_executable
        self.runner = Path(__file__).with_name("clarabel_runner.jl")

    @staticmethod
    def bundled_project() -> Path:
        """Return the package-shipped Julia environment for Clarabel."""
        return Path(__file__).with_name("julia")

    def _ensure_environment(self) -> bool:
        completed = subprocess.run(
            [
                self.julia_executable,
                f"--project={self.clarabel_project}",
                "-e",
                "using Pkg; Pkg.instantiate(); using Clarabel",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        return completed.returncode == 0

    def available(self) -> bool:
        """Return whether Julia and the configured Clarabel project are usable."""
        if not self.clarabel_project.is_dir() or not self.runner.is_file():
            return False
        try:
            if not self._ensure_environment():
                return False
            completed = subprocess.run(
                [
                    self.julia_executable,
                    f"--project={self.clarabel_project}",
                    "-e",
                    "using Clarabel; print(Clarabel.VERSION)",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    def solve(self, problem: dict[str, Any], *, timeout: float | None = None) -> ClarabelResult:
        """Solve a JSON-compatible sparse conic problem with Clarabel."""
        completed = subprocess.run(
            [
                self.julia_executable,
                f"--project={self.clarabel_project}",
                str(self.runner),
            ],
            input=json.dumps(problem),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Clarabel.jl failed ({completed.returncode}): {detail}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Clarabel.jl returned invalid JSON: {completed.stdout[-500:]}"
            ) from error
        if result.get("error"):
            raise RuntimeError(f"Clarabel.jl rejected the problem: {result['error']}")
        return ClarabelResult(
            status=str(result["status"]),
            x=[float(value) for value in result.get("x", [])],
            z=[float(value) for value in result.get("z", [])],
            s=[float(value) for value in result.get("s", [])],
            objective=(
                float(result["objective"]) if result.get("objective") is not None else None
            ),
            iterations=int(result.get("iterations", 0)),
            solve_time=(
                float(result["solve_time"]) if result.get("solve_time") is not None else None
            ),
        )


__all__ = ["ClarabelBridge", "ClarabelResult"]
