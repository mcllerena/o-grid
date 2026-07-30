from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from o_grid import ParsedAnaredeSystem


def _ensure_repo_src_paths() -> None:
    """Allow direct execution without installing local sibling repositories."""
    this_repo_root = Path(__file__).resolve().parents[1]
    o_grid_src = this_repo_root / "src"
    sibling_r2x_core_src = this_repo_root.parent / "r2x-core" / "src"

    for candidate in (o_grid_src, sibling_r2x_core_src):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_ensure_repo_src_paths()


def _load_r2x_core_or_shims() -> tuple[type, Any, type, type, Any]:
    """Load r2x-core symbols or provide lightweight shims when unavailable."""
    try:
        from r2x_core import DataStore, Ok, Plugin, PluginConfig, PluginContext

        return DataStore, Ok, Plugin, PluginConfig, PluginContext
    except ModuleNotFoundError as error:
        print(
            "Warning: r2x-core dependencies are not fully available "
            f"({error}). Using local compatibility shims."
        )

        @dataclass
        class _OkResult:
            value: Any

            def is_err(self) -> bool:
                return False

            def ok(self) -> Any:
                return self.value

        def _ok(value: Any) -> _OkResult:
            return _OkResult(value)

        class _PluginConfig:
            def __init__(self, **kwargs: Any) -> None:
                for key, value in kwargs.items():
                    setattr(self, key, value)

        class _DataStore:
            def __init__(self, path: str | Path) -> None:
                self.path = Path(path)

        class _PluginContext:
            def __init__(self, config: Any, store: Any = None) -> None:
                self.config = config
                self.store = store
                self.system = None
                self.metadata: dict[str, Any] = {}

        class _Plugin:
            _ctx: Any

            @classmethod
            def from_context(cls, ctx: Any) -> Any:
                instance = cls()
                instance._ctx = ctx
                return instance

            @property
            def ctx(self) -> Any:
                return self._ctx

            @property
            def config(self) -> Any:
                return self._ctx.config

            def run(self) -> Any:
                result = self.on_build()
                self._ctx.system = result.ok()
                return self._ctx

        return _DataStore, _ok, _Plugin, _PluginConfig, _PluginContext


DataStore, Ok, Plugin, PluginConfig, PluginContext = _load_r2x_core_or_shims()


class AnaredeConfig(PluginConfig):
    """Configuration for ANAREDE parser example."""

    model_year: int = 2029
    system_name: str = "ANAREDE"
    pwf_path: str


class AnaredeParser(Plugin):
    """Thin r2x_core Plugin wrapper around o_grid ANAREDE parsing."""

    def on_build(self):
        from o_grid import parse_anarede_system

        parsed = parse_anarede_system(
            Path(self.config.pwf_path),
            system_name=self.config.system_name,
        )
        self.ctx.metadata["parsed"] = parsed
        return Ok(parsed.system)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _anarede_data_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "tests" / "data" / "anarede"


def list_cases() -> list[Path]:
    """Return all .pwf test cases available under tests/data/anarede."""
    return sorted(_anarede_data_dir().glob("*.pwf"))


def print_cases() -> None:
    """Print available ANAREDE test files."""
    cases = list_cases()
    if not cases:
        print("No .pwf files found in tests/data/anarede")
        return

    print("Available ANAREDE cases:")
    for case in cases:
        print(f"- {case.name}")


def resolve_case(pwf: str | Path = "d_9nodes.pwf") -> Path:
    """Resolve a .pwf case from an absolute path, relative path, or case filename."""
    pwf_path = Path(pwf)
    if pwf_path.is_absolute() and pwf_path.exists():
        return pwf_path

    if pwf_path.exists():
        return pwf_path.resolve()

    case_from_data_dir = _anarede_data_dir() / pwf_path
    if case_from_data_dir.exists():
        return case_from_data_dir.resolve()

    available = ", ".join(case.name for case in list_cases())
    raise FileNotFoundError(f"Could not find case '{pwf}'. Available files: {available}")


def parse_case(
    pwf: str | Path = "d_9nodes.pwf", *, system_name: str = "ANAREDE"
) -> ParsedAnaredeSystem:
    """Parse one ANAREDE case through r2x_core PluginContext flow."""
    pwf_path = resolve_case(pwf)
    parse_cfg = AnaredeConfig(
        model_year=2029,
        system_name=system_name,
        pwf_path=str(pwf_path),
    )
    parse_ctx = PluginContext(config=parse_cfg, store=DataStore(path=pwf_path.parent))
    result_ctx = AnaredeParser.from_context(parse_ctx).run()
    return result_ctx.metadata["parsed"]


def print_summary(parsed: ParsedAnaredeSystem, sample_count: int = 2) -> None:
    """Print parsed system summary and sample records."""

    print(f"Source file: {parsed.source}")
    print(f"System name: {parsed.system.name}")
    system_title = (parsed.system.description or "").strip()
    if system_title:
        print(f"Title: {system_title}")
    print(f"Parsed blocks: {len(parsed.components_by_block)}")

    total_components = 0
    for block in sorted(parsed.components_by_block):
        records = parsed.components_by_block[block]
        total_components += len(records)
        class_name = parsed.component_classes[block].__name__
        print(f"- {block:10} -> {class_name:28} records={len(records)}")

    print(f"Total components in infrasys System: {total_components}")

    sample_count = max(0, sample_count)
    if sample_count == 0:
        return

    print("\nSample records:")
    for block in sorted(parsed.components_by_block):
        records = parsed.components_by_block[block][:sample_count]
        if not records:
            continue
        print(f"\n[{block}] first {len(records)} record(s)")
        for record in records:
            payload = record.model_dump(exclude={"uuid", "raw_line"})
            print(payload)


def run_case(pwf: str | Path = "d_9nodes.pwf", sample_count: int = 2) -> int:
    """Convenience runner for script and interactive sessions."""
    parsed = parse_case(pwf)
    print_summary(parsed, sample_count=sample_count)
    return 0


# r2x-sienna style top-level workflow variables
data_path = resolve_case("d_9nodes.pwf")
out_path = _repo_root() / "output" / "system.json"

# Parse
parse_cfg = AnaredeConfig(
    model_year=2029,
    system_name="ANAREDE-9",
    pwf_path=str(data_path),
)
parse_ctx = PluginContext(config=parse_cfg, store=DataStore(path=data_path.parent))
result_ctx = AnaredeParser.from_context(parse_ctx).run()
parsed_system = result_ctx.system
parsed_payload: ParsedAnaredeSystem = result_ctx.metadata["parsed"]


def main() -> int:
    """Run the default ANAREDE case when the script is executed directly."""
    print_summary(parsed_payload, sample_count=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
