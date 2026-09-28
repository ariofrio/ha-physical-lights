"""Runtime bridge to a configured Physical Lights calibrated proxy."""

from ..calibrated.api import get_calibrated_light


def calibrated_source(hass, entity_id):
    """Resolve the source afresh after source-entry reloads."""
    return get_calibrated_light(hass, entity_id)
