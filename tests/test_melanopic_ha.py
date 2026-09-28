"""Melanopic Light interaction with a real Calibrated Light instance."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def setup_layers(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_OFF,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "min_color_temp_kelvin": 2200,
            "max_color_temp_kelvin": 6500,
        },
    )
    calibrated = MockConfigEntry(
        domain="physical_lights",
        title="Calibrated Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "kind": "calibrated",
            "name": "Calibrated Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    calibrated.add_to_hass(hass)
    assert await hass.config_entries.async_setup(calibrated.entry_id)
    await hass.async_block_till_done()
    melanopic = MockConfigEntry(
        domain="physical_lights",
        title="Melanopic Bedroom Lamp",
        data={
            "kind": "melanopic",
            "name": "Melanopic Bedroom Lamp",
            "source_entity_id": "light.calibrated_bedroom_lamp",
        },
    )
    melanopic.add_to_hass(hass)
    assert await hass.config_entries.async_setup(melanopic.entry_id)
    await hass.async_block_till_done()
    return calibrated, melanopic


async def test_all_three_device_types_share_one_integration_without_crossing_actions(hass):
    calibrated, melanopic = await setup_layers(hass)
    daylight = MockConfigEntry(
        domain="physical_lights",
        title="Daylight",
        data={"kind": "daylight"},
    )
    daylight.add_to_hass(hass)
    assert await hass.config_entries.async_setup(daylight.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.daylight_illuminance") is not None
    assert hass.states.get("light.calibrated_bedroom_lamp") is not None
    assert hass.states.get("light.melanopic_bedroom_lamp") is not None

    registry = dr.async_get(hass)
    daylight_device = registry.async_get_device_by_identifier(
        ("physical_lights", daylight.entry_id), daylight.entry_id
    )
    calibrated_device = registry.async_get_device_by_identifier(
        ("physical_lights", calibrated.entry_id), calibrated.entry_id
    )
    assert daylight_device is not None and calibrated_device is not None
    result = await hass.services.async_call(
        "physical_lights",
        "from_elevation",
        {"device_id": daylight_device.id, "geometric_elevation": 20},
        blocking=True,
        return_response=True,
    )
    assert result["lux"] > 0
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "physical_lights",
            "from_elevation",
            {"device_id": calibrated_device.id, "geometric_elevation": 20},
            blocking=True,
            return_response=True,
        )
    assert melanopic.entry_id in hass.data["physical_lights"]


def intercept_raw_light(hass, monkeypatch):
    calls = []
    service_class = type(hass.services)
    original = service_class.async_call

    async def call(self, domain, service, data=None, **kwargs):
        if domain == "light" and data and data.get("entity_id") == "light.raw_bedroom_lamp":
            calls.append((service, data))
            previous = hass.states.get("light.raw_bedroom_lamp")
            attributes = dict(previous.attributes) if previous else {}
            if service == "turn_on":
                if "color_temp_kelvin" in data:
                    attributes.update(
                        color_mode="color_temp",
                        color_temp_kelvin=data["color_temp_kelvin"],
                        effect=None,
                    )
                if "brightness" in data:
                    attributes["brightness"] = data["brightness"]
                hass.states.async_set("light.raw_bedroom_lamp", STATE_ON, attributes)
            else:
                hass.states.async_set("light.raw_bedroom_lamp", STATE_OFF, attributes)
            return None
        return await original(self, domain, service, data, **kwargs)

    monkeypatch.setattr(service_class, "async_call", call)
    return calls


async def test_edi_target_controls_underlying_lux_and_reports_achieved(hass, monkeypatch):
    await setup_layers(hass)
    calls = intercept_raw_light(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 60},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[-1][1]["color_temp_kelvin"] == 4000
    assert (
        89 < float(hass.states.get("number.calibrated_bedroom_lamp_target_illuminance").state) < 92
    )
    assert float(
        hass.states.get("sensor.melanopic_bedroom_lamp_estimated_melanopic_edi").state
    ) == pytest.approx(60, abs=1)


async def test_proxy_cct_is_preference_and_underlying_cct_is_actual(hass, monkeypatch):
    await setup_layers(hass)
    calls = intercept_raw_light(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.melanopic_bedroom_lamp", "color_temp_kelvin": 6500},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    actual = calls[-1][1]["color_temp_kelvin"]
    assert 4600 < actual < 5000
    assert hass.states.get("light.melanopic_bedroom_lamp").attributes["color_temp_kelvin"] == 6500
    assert (
        hass.states.get("light.calibrated_bedroom_lamp").attributes["color_temp_kelvin"] == actual
    )
    assert float(
        hass.states.get("sensor.melanopic_bedroom_lamp_estimated_melanopic_edi").state
    ) == pytest.approx(100, abs=1)


async def test_cct_adjustment_limit_clips_and_then_restores_edi(hass, monkeypatch):
    await setup_layers(hass)
    calls = intercept_raw_light(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.melanopic_bedroom_lamp", "color_temp_kelvin": 6500},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_maximum_cct_adjustment", "value": 0},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert calls[-1][1]["color_temp_kelvin"] == 6500
    assert (
        float(hass.states.get("sensor.melanopic_bedroom_lamp_estimated_melanopic_edi").state) < 85
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_maximum_cct_adjustment", "value": 2500},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert 4600 < calls[-1][1]["color_temp_kelvin"] < 5000
    assert hass.states.get("number.melanopic_bedroom_lamp_target_melanopic_edi").state == "100.0"


async def test_target_survives_off_on(hass, monkeypatch):
    await setup_layers(hass)
    calls = intercept_raw_light(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 60},
        blocking=True,
    )
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.melanopic_bedroom_lamp"}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.melanopic_bedroom_lamp"}, blocking=True
    )
    await hass.async_block_till_done()
    assert calls[-1][0] == "turn_on"
    assert hass.states.get("number.melanopic_bedroom_lamp_target_melanopic_edi").state == "60.0"


async def test_request_and_preference_survive_reload(hass, monkeypatch):
    _, melanopic = await setup_layers(hass)
    intercept_raw_light(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.melanopic_bedroom_lamp", "color_temp_kelvin": 6500},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_maximum_cct_adjustment", "value": 0},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 100},
        blocking=True,
    )
    assert await hass.config_entries.async_reload(melanopic.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.melanopic_bedroom_lamp_target_melanopic_edi").state == "100.0"
    assert hass.states.get("number.melanopic_bedroom_lamp_maximum_cct_adjustment").state == "0"
    assert hass.states.get("light.melanopic_bedroom_lamp").attributes["color_temp_kelvin"] == 6500


async def test_unmodeled_color_makes_edi_unavailable(hass):
    await setup_layers(hass)
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "color_mode": "rgbww",
            "rgbww_color": (20, 40, 80, 0, 0),
            "brightness": 100,
        },
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.melanopic_bedroom_lamp_estimated_melanopic_edi").state
        == "unavailable"
    )


async def test_rebinds_when_calibrated_reference_changes(hass, monkeypatch):
    await setup_layers(hass)
    calls = intercept_raw_light(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 60},
        blocking=True,
    )
    first_brightness = calls[-1][1]["brightness"]
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.calibrated_bedroom_lamp_reference_illuminance", "value": 200},
        blocking=True,
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.melanopic_bedroom_lamp_target_melanopic_edi", "value": 60},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert calls[-1][1]["brightness"] < first_brightness
    assert float(
        hass.states.get("sensor.melanopic_bedroom_lamp_estimated_melanopic_edi").state
    ) == pytest.approx(60, abs=1)
