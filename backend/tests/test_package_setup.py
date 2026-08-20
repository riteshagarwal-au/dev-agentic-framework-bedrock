"""Sanity test confirming the pytest/package tooling is wired correctly.

This is scaffolding only (Task 1.2) — it verifies the `daf` package is
importable and pytest can discover/run tests, not any business logic.
"""

import daf


def test_daf_package_is_importable():
    assert daf.__version__ == "0.1.0"


def test_pytest_runs():
    assert 1 + 1 == 2
