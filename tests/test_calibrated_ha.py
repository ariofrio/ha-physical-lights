"""Configuration, command, state, and persistence behavior in Home Assistant."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.physical_lights.calibrated.api import get_calibrated_light


async def setup_proxy(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_OFF,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 4,
            "effect_list": ["Party", "Candlelight"],
            "min_color_temp_kelvin": 2200,
            "max_color_temp_kelvin": 6500,
        },
    )
    entry = MockConfigEntry(
        domain="physical_lights",
        title="Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "kind": "calibrated",
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_lists_measured_model_and_source(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_OFF,
        {"supported_color_modes": ["color_temp"]},
    )
    form = await hass.config_entries.flow.async_init("physical_lights", context={"source": "user"})
    form = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"next_step_id": "calibrated"}
    )
    assert form["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    assert result["type"] == "create_entry"


async def test_new_proxy_imports_saved_request_from_matching_legacy_entry(hass):
    legacy = MockConfigEntry(
        domain="calibrated_light",
        title="Calibrated Bedroom Lamp",
        data={
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    legacy.add_to_hass(hass)
    await Store(hass, 1, f"calibrated_light.{legacy.entry_id}").async_save(
        {"target_lux": 13.79, "kelvin": 3000}
    )
    proxy = await setup_proxy(hass)
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "13.8"
    assert hass.data["physical_lights"][proxy.entry_id].kelvin == 3000
    assert await Store(hass, 1, f"physical_lights.{proxy.entry_id}").async_load() == {
        "target_lux": 13.79,
        "kelvin": 3000,
        "last_raw_settings": None,
    }
    assert hass.states.get("light.raw_bedroom_lamp").state == STATE_OFF


def intercept_source(hass, monkeypatch):
    calls = []
    service_class = type(hass.services)
    original = service_class.async_call

    async def call(self, domain, service, data=None, **kwargs):
        if domain == "light" and data and data.get("entity_id") == "light.raw_bedroom_lamp":
            calls.append((service, data))
            if service == "turn_on":
                previous = hass.states.get("light.raw_bedroom_lamp")
                attributes = dict(previous.attributes) if previous else {}
                if "color_temp_kelvin" in data:
                    attributes.update(
                        color_mode="color_temp",
                        color_temp_kelvin=data["color_temp_kelvin"],
                        effect=None,
                    )
                elif "rgbww_color" in data:
                    attributes.update(
                        color_mode="rgbww", rgbww_color=data["rgbww_color"], effect=None
                    )
                elif "effect" in data:
                    attributes.update(color_mode="brightness", effect=data["effect"])
                if "brightness" in data:
                    attributes["brightness"] = data["brightness"]
                hass.states.async_set(
                    "light.raw_bedroom_lamp",
                    STATE_ON,
                    attributes,
                )
            elif service == "turn_off":
                source = hass.states.get("light.raw_bedroom_lamp")
                hass.states.async_set(
                    "light.raw_bedroom_lamp",
                    STATE_OFF,
                    dict(source.attributes) if source else {},
                )
            return None
        return await original(self, domain, service, data, **kwargs)

    monkeypatch.setattr(service_class, "async_call", call)
    return calls


async def test_entities_track_source_and_preserve_target_on_clip(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    assert hass.states.get("number.bedroom_lamp_target_illuminance") is not None
    assert hass.states.get("number.bedroom_lamp_reference_illuminance") is not None
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance") is not None
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 120},
        blocking=True,
    )
    assert calls[-1][1]["color_temp_kelvin"] == 4001
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "color_temp_kelvin": 2200},
        blocking=True,
    )
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "120.0"
    assert calls[-1][1]["brightness"] == 255
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "color_temp_kelvin": 4001},
        blocking=True,
    )
    assert calls[-1][1]["brightness"] < 255


async def test_public_port_atomically_sets_lux_and_cct(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    port = get_calibrated_light(hass, "light.bedroom_lamp")
    assert port is not None
    assert port.min_lux(4000) < 90 < port.max_lux(4000)
    await port.async_set_output(90, 4000)
    assert len(calls) == 1
    assert calls[-1][1]["color_temp_kelvin"] == 4000
    assert float(hass.states.get("number.bedroom_lamp_target_illuminance").state) == 90
    assert port.estimated_lux() == pytest.approx(90, abs=2)
    assert port.reported_kelvin() == 4000


async def test_off_and_on_restore_requested_values(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 90},
        blocking=True,
    )
    await hass.services.async_call(
        "light",
        "turn_off",
        {"entity_id": "light.bedroom_lamp"},
        blocking=True,
    )
    assert calls[-1] == ("turn_off", {"entity_id": "light.raw_bedroom_lamp"})
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp"},
        blocking=True,
    )
    assert calls[-1][1]["color_temp_kelvin"] == 4001
    assert calls[-1][1]["brightness"] > 0


async def test_proxy_forwards_transition_to_source(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            "entity_id": "light.bedroom_lamp",
            "brightness_pct": 100,
            "color_temp_kelvin": 4517,
            "transition": 600,
        },
        blocking=True,
    )
    assert calls[-1][1]["transition"] == 600
    await hass.services.async_call(
        "light",
        "turn_off",
        {"entity_id": "light.bedroom_lamp", "transition": 3},
        blocking=True,
    )
    assert calls[-1][1]["transition"] == 3


async def test_external_rgb_mode_makes_estimate_unavailable(hass):
    await setup_proxy(hass)
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {"color_mode": "rgbww", "brightness": 200, "rgbww_color": [0, 0, 0, 50, 50]},
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state == "unavailable"


async def test_rgbww_mode_uses_raw_brightness_and_preserves_white_target(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 50},
        blocking=True,
    )
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "rgbww_color": (20, 40, 80, 0, 0), "brightness": 64},
        blocking=True,
    )
    assert calls[-1][1] == {
        "entity_id": "light.raw_bedroom_lamp",
        "rgbww_color": (20, 40, 80, 0, 0),
        "brightness": 64,
    }
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 4,
            "effect_list": ["Party", "Candlelight"],
            "color_mode": "rgbww",
            "brightness": 64,
            "rgbww_color": (20, 40, 80, 0, 0),
        },
    )
    await hass.async_block_till_done()
    proxy = hass.states.get("light.bedroom_lamp")
    assert proxy.attributes["supported_color_modes"] == ["color_temp", "rgbww"]
    assert proxy.attributes["color_mode"] == "rgbww"
    assert proxy.attributes["rgbww_color"] == (20, 40, 80, 0, 0)
    assert proxy.attributes["brightness"] == 64
    assert proxy.attributes["effect_list"] == ["Party", "Candlelight"]
    assert proxy.attributes["supported_features"] & 4
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state == "unavailable"
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "50.0"

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "brightness": 100},
        blocking=True,
    )
    assert calls[-1][1] == {"entity_id": "light.raw_bedroom_lamp", "brightness": 100}
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "50.0"


async def test_color_picker_converts_to_source_rgbww_mode(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "rgb_color": (255, 0, 0)},
        blocking=True,
    )
    assert "rgbww_color" in calls[-1][1]
    assert "color_temp_kelvin" not in calls[-1][1]


async def test_effect_and_flash_follow_source_capabilities(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 12,
            "effect_list": ["Party"],
            "effect": "Party",
            "color_mode": "brightness",
            "brightness": 88,
        },
    )
    await hass.async_block_till_done()
    proxy = hass.states.get("light.bedroom_lamp")
    assert proxy.attributes["color_mode"] == "brightness"
    assert proxy.attributes["effect"] == "Party"
    assert proxy.attributes["brightness"] == 88
    assert proxy.attributes["supported_features"] & 8
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state == "unavailable"
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "effect": "Party", "flash": "short"},
        blocking=True,
    )
    assert calls[-1][1] == {
        "entity_id": "light.raw_bedroom_lamp",
        "effect": "Party",
        "flash": "short",
    }
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    assert calls[-1][1]["effect"] == "Party"
    assert calls[-1][1]["brightness"] == 88


async def test_explicit_kelvin_or_target_returns_to_calibrated_white(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 50},
        blocking=True,
    )
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 4,
            "color_mode": "rgbww",
            "brightness": 64,
            "rgbww_color": (20, 40, 80, 0, 0),
        },
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "color_temp_kelvin": 4001},
        blocking=True,
    )
    assert calls[-1][1]["color_temp_kelvin"] == 4001
    assert "rgbww_color" not in calls[-1][1]
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "50.0"
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state != "unavailable"
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 4,
            "color_mode": "rgbww",
            "brightness": 64,
            "rgbww_color": (20, 40, 80, 0, 0),
        },
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 60},
        blocking=True,
    )
    assert calls[-1][1]["color_temp_kelvin"] == 4001
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "60.0"


async def test_uncalibrated_color_survives_proxy_off_and_on(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 50},
        blocking=True,
    )
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 4,
            "color_mode": "rgbww",
            "rgbww_color": (20, 40, 80, 0, 0),
            "brightness": 64,
        },
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    assert calls[-1][1] == {
        "entity_id": "light.raw_bedroom_lamp",
        "rgbww_color": (20, 40, 80, 0, 0),
        "brightness": 64,
    }
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "50.0"


async def test_uncalibrated_color_survives_proxy_reload(hass, monkeypatch):
    entry = await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww"],
            "supported_features": 4,
            "color_mode": "rgbww",
            "rgbww_color": (20, 40, 80, 0, 0),
            "brightness": 64,
        },
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    assert calls[-1][1]["rgbww_color"] == [20, 40, 80, 0, 0]
    assert calls[-1][1]["brightness"] == 64


async def test_white_channel_mode_restores_its_raw_level(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp", "rgbww", "white"],
            "color_mode": "white",
            "brightness": 77,
        },
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    assert calls[-1][1] == {"entity_id": "light.raw_bedroom_lamp", "white": 77}
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.bedroom_lamp"}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.bedroom_lamp", "brightness": 100}, blocking=True
    )
    assert calls[-1][1] == {"entity_id": "light.raw_bedroom_lamp", "white": 100}


async def test_brightness_slider_controls_lux_and_reports_actual_raw_output(hass, monkeypatch):
    entry = await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "brightness": 128},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert 70 < float(hass.states.get("number.bedroom_lamp_target_illuminance").state) < 100
    assert calls[-1][1]["brightness"] > 128
    assert 70 < float(hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state) < 100
    assert abs(int(hass.states.get("light.bedroom_lamp").attributes["brightness"]) - 128) < 5
    target = hass.states.get("number.bedroom_lamp_target_illuminance")
    precise_target = hass.data["physical_lights"][entry.entry_id].target_lux
    assert target.state == str(round(precise_target, 1))
    assert target.attributes["max"] == 173.0


async def test_options_change_reference_and_persist_target(hass, monkeypatch):
    entry = await setup_proxy(hass)
    intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 120},
        blocking=True,
    )
    hass.config_entries.async_update_entry(entry, options={"reference_lux": 200})
    await hass.async_block_till_done()
    assert hass.states.get("number.bedroom_lamp_reference_illuminance").state == "200.0"
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "120.0"


async def test_configure_dialog_updates_model_selection_and_reference(hass):
    entry = await setup_proxy(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] == "form"
    assert {key.schema for key in form["data_schema"].schema} == {
        "source_entity_id",
        "model_id",
        "reference_lux",
    }
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 200,
        },
    )
    assert saved["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get("number.bedroom_lamp_reference_illuminance").state == "200.0"


async def test_configure_dialog_can_follow_a_source_entity_rename(hass):
    entry = await setup_proxy(hass)
    hass.states.async_set(
        "light.renamed_source",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp"],
            "color_mode": "color_temp",
            "brightness": 255,
            "color_temp_kelvin": 4001,
        },
    )
    form = await hass.config_entries.options.async_init(entry.entry_id)
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "source_entity_id": "light.renamed_source",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    assert saved["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get("light.bedroom_lamp").attributes["source_entity_id"] == (
        "light.renamed_source"
    )


async def test_new_proxy_adopts_current_white_light_instead_of_starting_at_maximum(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp"],
            "color_mode": "color_temp",
            "brightness": 41,
            "color_temp_kelvin": 3009,
        },
    )
    entry = MockConfigEntry(
        domain="physical_lights",
        title="Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "kind": "calibrated",
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    actual = float(hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state)
    requested = hass.data["physical_lights"][entry.entry_id].target_lux
    assert requested == pytest.approx(actual, abs=0.02)
    assert float(hass.states.get("number.bedroom_lamp_target_illuminance").state) == pytest.approx(
        actual, abs=0.051
    )


async def test_new_proxy_with_source_off_starts_at_minimum_on_target(hass):
    await setup_proxy(hass)
    target = float(hass.states.get("number.bedroom_lamp_target_illuminance").state)
    assert 0 < target < 10


async def test_proxy_adopts_late_source_state_after_startup(hass):
    entry = MockConfigEntry(
        domain="physical_lights",
        title="Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "kind": "calibrated",
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp"],
            "color_mode": "color_temp",
            "brightness": 41,
            "color_temp_kelvin": 3009,
        },
    )
    await hass.async_block_till_done()
    actual = float(hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state)
    requested = hass.data["physical_lights"][entry.entry_id].target_lux
    assert requested == pytest.approx(actual, abs=0.02)
    assert float(hass.states.get("number.bedroom_lamp_target_illuminance").state) == pytest.approx(
        actual, abs=0.051
    )
