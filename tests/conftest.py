import pytest

import custom_components  # noqa: F401  # Discover local components before HA patches imports.

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield
