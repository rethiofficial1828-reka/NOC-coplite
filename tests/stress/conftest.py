"""
Pytest configuration and CLI options for isolated stress-testing framework.
"""

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("stress", "NOC-Copilot Stress Testing Options")
    group.addoption(
        "--stress-run",
        action="store_true",
        default=False,
        help="Explicitly enable execution of stress testing suite during general pytest runs.",
    )
    group.addoption(
        "--stress-seed",
        action="store",
        default="42",
        type=int,
        help="Base random seed for deterministic scenario generation (default: 42).",
    )
    group.addoption(
        "--stress-case",
        action="store",
        default=None,
        type=str,
        help="Specific case ID to run and reproduce (e.g. STRESS-000007).",
    )
    group.addoption(
        "--stress-count",
        action="store",
        default=100,
        type=int,
        help="Number of stress test cases to execute (e.g. 100, 1000, 10000, 100000; default: 100).",
    )


@pytest.fixture
def stress_seed(request):
    return request.config.getoption("--stress-seed")


@pytest.fixture
def stress_case(request):
    return request.config.getoption("--stress-case")


@pytest.fixture
def stress_count(request):
    return request.config.getoption("--stress-count")


@pytest.fixture
def stress_run(request):
    return request.config.getoption("--stress-run")
