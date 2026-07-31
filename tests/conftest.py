from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_folder(pytestconfig: pytest.Config) -> Path:
    return pytestconfig.rootpath.joinpath("tests", "data")
