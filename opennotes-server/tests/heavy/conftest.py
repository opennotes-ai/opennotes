"""
Conftest for heavy tests.

Heavy tests are resource-intensive (e.g., matrix factorization) and must run
sequentially (-n 0) to avoid OOM-killing xdist workers. They share fixtures
with integration tests via import.
"""

from tests.integration.conftest import *  # noqa: F403
