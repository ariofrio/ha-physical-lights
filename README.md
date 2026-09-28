# Physical Lights for Home Assistant

Physical Lights is one Home Assistant integration with three device types:

| Device | What it provides |
| --- | --- |
| **Daylight reference** | Clear-sky illuminance, melanopic EDI, CCT, solar geometry, and two calculation actions for a configurable receiving surface. |
| **Calibrated light** | A light proxy with a lamp-only lux target at a measured position. It uses a bulb-specific white-light curve. |
| **Melanopic light** | A proxy above a Calibrated light. It targets lamp-only melanopic EDI while treating the light entity's CCT as a preference. |

```text
Sun + fixed atmosphere ──> Daylight reference ──> outdoor estimates

Physical bulb ──> Calibrated light ──> Melanopic light
                   lux at a position     EDI target + preferred CCT
```

The daylight model is not a weather forecast. The lamp models estimate the bulb's contribution at one calibrated position; they do not measure total room exposure.

## Install

Requires Home Assistant 2026.9 or newer. In HACS, add `ariofrio/ha-physical-lights` as a custom repository of type **Integration**, download **Physical Lights**, and restart Home Assistant. Then choose **Settings → Devices & services → Add integration → Physical Lights** and select a device type. Add another entry for each receiving surface or light.

[Add the HACS repository](https://my.home-assistant.io/redirect/hacs_repository/?owner=ariofrio&repository=ha-physical-lights&category=integration) · [Add a Physical Lights device](https://my.home-assistant.io/redirect/config_flow_start/?domain=physical_lights)

For manual installation, copy `custom_components/physical_lights/` into the Home Assistant configuration directory and restart.

This replaces the separate [Daylight](https://github.com/ariofrio/ha-daylight) and [Calibrated Light](https://github.com/ariofrio/ha-calibrated-light) repositories. Both can remain installed while you set up and compare the new devices. To migrate, record the old entries' names, options, and entity IDs; create matching Physical Lights devices; compare their output; update references to the new entities; then remove the old entries and HACS downloads. On first setup, a Calibrated light copies the saved target lux and CCT from one old Calibrated Light entry using the same source and bulb model. Entity IDs and recorder history are not transferred automatically. Back up Home Assistant before deleting the old entries. A separately published Melanopic Light was never required; its functionality is included here.

## Daylight reference

Each Daylight entry creates six synchronized sensors: illuminance (lx), melanopic equivalent daylight illuminance (EDI, lx), CCT (K), normalized level, geometric solar elevation, and today's noon solar elevation. They update every minute from Home Assistant's location and time zone. Add multiple Daylight entries to model different receiving surfaces.

**Configure** sets tilt (0° horizontal, 90° vertical), fixed compass bearing, or follow-the-sun orientation. The review step plots illuminance, EDI, and CCT over the local day before saving. The live sensors and preview use the same directional calculation, including direct sun, diffuse sky, and ground contribution. It is a fixed-atmosphere estimate with a modeled twilight tail; it does not use current clouds or aerosol observations. CCT can be unavailable when the simulated spectrum is numerically ambiguous.

The `physical_lights.from_elevation` and `physical_lights.from_level` actions calculate a result for a selected Daylight device without changing state. Both return lux, melanopic EDI, CCT, quality, and geometry. `from_elevation` takes **geometric** solar elevation; Home Assistant's ordinary `sun.sun` elevation is apparent and can shift the result near the horizon. The optional solar azimuth defaults to its *current* direction, so supply an explicit azimuth when evaluating a hypothetical time on a fixed-facing surface.

```yaml
- action: physical_lights.from_level
  data:
    device_id: "<daylight-device-id>"
    daylight_level: 0.35
  response_variable: daylight_result
```

Level 0 is the dark reference at −18° geometric elevation; level 1 is today's solar noon. Level is linear in solar elevation, not lux. See the [daylight model](docs/daylight/model.md) and [offline generation procedure](tools/README.md).

## Calibrated light

Choose a tunable-white source light and a measured bulb model. The first profile is the [Philips WiZ 21 W A23, model 9290034999](https://www.usa.lighting.philips.com/consumer/p/smart-led-bulb-21w-eq150w-a23-e26/046677578718). Other WiZ devices can report the same broad HA model string, so check the bulb label before selecting this profile.

Measure illuminance at the position and meter orientation you care about, first with the lamp off and then at **4000 K and 100%**. Enter `on − off` in lx as the reference illuminance. Keep the meter and other lights unchanged, and take the pair close enough together that daylight does not drift appreciably. The example measurement at Andres's bed was 198 − 25 = **173 lx**. A separate 50% reading was 78 lx lamp-only versus about 77.4 lx predicted. Recalibrate at a different position; the 173 lx measurement does not transfer to another location.

For a device named Bedroom Lamp, the integration creates `light.bedroom_lamp`, `number.bedroom_lamp_target_illuminance`, `sensor.bedroom_lamp_estimated_illuminance`, and `number.bedroom_lamp_reference_illuminance`. HA assigns entity IDs, so names can vary. In white mode the brightness slider spans achievable lamp-only lux at the selected CCT. Changing CCT preserves the requested lux; if it exceeds that CCT's maximum, the bulb clips while the target stays saved. Returning to a wider range restores the target. Zero lux turns the light off. Off/on preserves the target and CCT. Color and effects pass through to the source, but their lux estimate is unavailable and their brightness slider uses the raw source scale.

The fitted white-light model uses the measured dimming and CCT curves: `predicted lx = reference lx × dimming_fraction(D) × peak_output(CCT) / peak_output(4000 K)`. It is **not** an absolute lumen estimate. Shade and room spectral transmission across CCT, bulb variation, meter geometry, and ambient subtraction all affect accuracy. See [measurements](docs/calibrated/original-measurements.csv) and [model limitations](docs/calibrated/model.md).

## Melanopic light

Create a Calibrated light first, then add a Melanopic light entry selecting it. The Melanopic proxy exposes a light entity, target EDI number, estimated achieved EDI sensor, and maximum CCT adjustment number. Its light entity's `color_temp_kelvin` is the **preferred** CCT. The underlying Calibrated light shows the CCT commanded to the source, which can differ. That source value is a reported setting, not a color-meter measurement.

The controller keeps the preferred CCT when it can reach the EDI target there. Otherwise it chooses the closest feasible CCT within `preferred ± maximum adjustment`; if the target is still unreachable, it clips output while keeping the requested target. Brightness maps across the modeled achievable EDI range. The estimated EDI sensor uses the source's reported lux and CCT. RGB/effects and CCT below 2700 K are outside this EDI model.

The current spectral conversion uses [TRILUX's representative CRI 90 LED melanopic daylight efficacy ratios](https://www.trilux.com/fileadmin/Downloads/Brochures/HCL/23_26-TwoPager_HCL_DE_230321.pdf): 0.45 at 2700 K, 0.49 at 3000 K, 0.66 at 4000 K, and 0.94 at 6500 K, with linear interpolation and no dimming dependence. These are **not measured spectra of the WiZ A23**. CCT and photopic lux alone cannot determine melanopic EDI for an arbitrary bulb; the [CIE method](https://files.cie.co.at/CIE_TN_015_2023.pdf) requires a spectral power distribution. For biologically relevant eye-level exposure, measure the Calibrated reference at eye position facing the relevant direction. The original 173 lx bed reading did not record meter orientation. Daylight through windows and other lamps are not included.

## Development and licenses

```sh
uv run --no-project --with-requirements requirements-test.txt ruff check custom_components/physical_lights tests tools
uv run --no-project --with-requirements requirements-test.txt ruff format --check custom_components/physical_lights tests tools
uv run --no-project --with-requirements requirements-test.txt pytest -q
```

The code is MIT licensed. CIE source weighting data and derived daylight melanopic values carry separate CC BY-SA 4.0 terms; see [scientific data attribution](NOTICE.md). Initial code and documentation were written by Codex at Andres Riofrio's direction; the lamp measurements were supplied by Andres.
