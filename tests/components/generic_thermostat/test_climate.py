"""The tests for the generic_thermostat."""
import datetime
from unittest.mock import patch

import pytest
import voluptuous as vol

from homeassistant import config as hass_config
from homeassistant.components import input_boolean, switch
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    DOMAIN,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_NONE,
    PRESET_SLEEP,
)
from homeassistant.components.generic_thermostat import (
    DOMAIN as GENERIC_THERMOSTAT_DOMAIN,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    SERVICE_RELOAD,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)
import homeassistant.core as ha
from homeassistant.core import DOMAIN as HASS_DOMAIN, CoreState, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM

from tests.common import (
    assert_setup_component,
    async_fire_time_changed,
    async_mock_service,
    get_fixture_path,
    mock_restore_cache,
)
from tests.components.climate import common

ENTITY = "climate.test"
ENT_SENSOR = "sensor.test"
ENT_SWITCH = "switch.test"
HEAT_ENTITY = "climate.test_heat"
COOL_ENTITY = "climate.test_cool"
ATTR_AWAY_MODE = "away_mode"
MIN_TEMP = 3.0
MAX_TEMP = 65.0
TARGET_TEMP = 42.0
COLD_TOLERANCE = 0.5
HOT_TOLERANCE = 0.5


async def test_setup_missing_conf(hass):
    """Test set up heat_control with missing config values."""
    config = {
        "platform": "generic_thermostat",
        "name": "test",
        "target_sensor": ENT_SENSOR,
    }
    with assert_setup_component(0):
        await async_setup_component(hass, "climate", {"climate": config})


async def test_valid_conf(hass):
    """Test set up generic_thermostat with valid config values."""
    assert await async_setup_component(
        hass,
        "climate",
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
            }
        },
    )


@pytest.fixture
async def setup_comp_1(hass):
    """Initialize components."""
    hass.config.units = METRIC_SYSTEM
    assert await async_setup_component(hass, "homeassistant", {})
    await hass.async_block_till_done()


async def test_heater_input_boolean(hass, setup_comp_1):
    """Test heater switching input_boolean."""
    heater_switch = "input_boolean.test"
    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )

    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "heater": heater_switch,
                "target_sensor": ENT_SENSOR,
                "initial_hvac_mode": HVAC_MODE_HEAT,
            }
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get(heater_switch).state == STATE_OFF

    _setup_sensor(hass, 18)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 23)

    assert hass.states.get(heater_switch).state == STATE_ON


async def test_heater_switch(hass, setup_comp_1, enable_custom_integrations):
    """Test heater switching test switch."""
    platform = getattr(hass.components, "test.switch")
    platform.init()
    switch_1 = platform.ENTITIES[1]
    assert await async_setup_component(
        hass, switch.DOMAIN, {"switch": {"platform": "test"}}
    )
    await hass.async_block_till_done()
    heater_switch = switch_1.entity_id

    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "heater": heater_switch,
                "target_sensor": ENT_SENSOR,
                "initial_hvac_mode": HVAC_MODE_HEAT,
            }
        },
    )

    await hass.async_block_till_done()
    assert hass.states.get(heater_switch).state == STATE_OFF

    _setup_sensor(hass, 18)
    await common.async_set_temperature(hass, 23)
    await hass.async_block_till_done()

    assert hass.states.get(heater_switch).state == STATE_ON


async def test_unique_id(hass, setup_comp_1):
    """Test heater switching input_boolean."""
    unique_id = "some_unique_id"
    _setup_sensor(hass, 18)
    _setup_switch(hass, True)
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "unique_id": unique_id,
            }
        },
    )
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)

    entry = entity_registry.async_get(ENTITY)
    assert entry
    assert entry.unique_id == unique_id


def _setup_sensor(hass, temp):
    """Set up the test sensor."""
    hass.states.async_set(ENT_SENSOR, temp)


@pytest.fixture
async def setup_comp_2(hass):
    """Initialize components."""
    hass.config.units = METRIC_SYSTEM
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 2,
                "hot_tolerance": 4,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "away_temp": 16,
                "sleep_temp": 17,
                "home_temp": 19,
                "comfort_temp": 20,
                "activity_temp": 21,
                "initial_hvac_mode": HVAC_MODE_HEAT,
            }
        },
    )
    await hass.async_block_till_done()


async def test_setup_defaults_to_unknown(hass):
    """Test the setting of defaults to unknown."""
    hass.config.units = METRIC_SYSTEM
    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 2,
                "hot_tolerance": 4,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "away_temp": 16,
            }
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == HVAC_MODE_OFF


async def test_setup_gets_current_temp_from_sensor(hass):
    """Test that current temperature is updated on entity addition."""
    hass.config.units = METRIC_SYSTEM
    _setup_sensor(hass, 18)
    await hass.async_block_till_done()
    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 2,
                "hot_tolerance": 4,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "away_temp": 16,
            }
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["current_temperature"] == 18


async def test_default_setup_params(hass, setup_comp_2):
    """Test the setup with default parameters."""
    state = hass.states.get(ENTITY)
    assert state.attributes.get("min_temp") == 7
    assert state.attributes.get("max_temp") == 35
    assert state.attributes.get("temperature") == 7


async def test_get_hvac_modes(hass, setup_comp_2):
    """Test that the operation list returns the correct modes."""
    state = hass.states.get(ENTITY)
    modes = state.attributes.get("hvac_modes")
    assert modes == [HVAC_MODE_HEAT, HVAC_MODE_OFF]


async def test_set_target_temp(hass, setup_comp_2):
    """Test the setting of the target temperature."""
    await common.async_set_temperature(hass, 30)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == 30.0
    with pytest.raises(vol.Invalid):
        await common.async_set_temperature(hass, None)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == 30.0


@pytest.mark.parametrize(
    "preset,temp",
    [
        (PRESET_NONE, 23),
        (PRESET_AWAY, 16),
        (PRESET_COMFORT, 20),
        (PRESET_HOME, 19),
        (PRESET_SLEEP, 17),
        (PRESET_ACTIVITY, 21),
    ],
)
async def test_set_away_mode(hass, setup_comp_2, preset, temp):
    """Test the setting away mode."""
    await common.async_set_temperature(hass, 23)
    await common.async_set_preset_mode(hass, preset)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == temp


@pytest.mark.parametrize(
    "preset,temp",
    [
        (PRESET_NONE, 23),
        (PRESET_AWAY, 16),
        (PRESET_COMFORT, 20),
        (PRESET_HOME, 19),
        (PRESET_SLEEP, 17),
        (PRESET_ACTIVITY, 21),
    ],
)
async def test_set_away_mode_and_restore_prev_temp(hass, setup_comp_2, preset, temp):
    """Test the setting and removing away mode.

    Verify original temperature is restored.
    """
    await common.async_set_temperature(hass, 23)
    await common.async_set_preset_mode(hass, preset)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == temp
    await common.async_set_preset_mode(hass, PRESET_NONE)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == 23


@pytest.mark.parametrize(
    "preset,temp",
    [
        (PRESET_NONE, 23),
        (PRESET_AWAY, 16),
        (PRESET_COMFORT, 20),
        (PRESET_HOME, 19),
        (PRESET_SLEEP, 17),
        (PRESET_ACTIVITY, 21),
    ],
)
async def test_set_away_mode_twice_and_restore_prev_temp(
    hass, setup_comp_2, preset, temp
):
    """Test the setting away mode twice in a row.

    Verify original temperature is restored.
    """
    await common.async_set_temperature(hass, 23)
    await common.async_set_preset_mode(hass, preset)
    await common.async_set_preset_mode(hass, preset)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == temp
    await common.async_set_preset_mode(hass, PRESET_NONE)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == 23


async def test_set_preset_mode_invalid(hass, setup_comp_2):
    """Test an invalid mode raises an error and ignore case when checking modes."""
    await common.async_set_temperature(hass, 23)
    await common.async_set_preset_mode(hass, "away")
    state = hass.states.get(ENTITY)
    assert state.attributes.get("preset_mode") == "away"
    await common.async_set_preset_mode(hass, "none")
    state = hass.states.get(ENTITY)
    assert state.attributes.get("preset_mode") == "none"
    with pytest.raises(ValueError):
        await common.async_set_preset_mode(hass, "Sleep")
    state = hass.states.get(ENTITY)
    assert state.attributes.get("preset_mode") == "none"


async def test_sensor_bad_value(hass, setup_comp_2):
    """Test sensor that have None as state."""
    state = hass.states.get(ENTITY)
    temp = state.attributes.get("current_temperature")

    _setup_sensor(hass, None)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.attributes.get("current_temperature") == temp

    _setup_sensor(hass, "inf")
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.attributes.get("current_temperature") == temp

    _setup_sensor(hass, "nan")
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.attributes.get("current_temperature") == temp


async def test_sensor_unknown(hass):
    """Test when target sensor is Unknown."""
    hass.states.async_set("sensor.unknown", STATE_UNKNOWN)
    assert await async_setup_component(
        hass,
        "climate",
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "unknown",
                "heater": ENT_SWITCH,
                "target_sensor": "sensor.unknown",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.unknown")
    assert state.attributes.get("current_temperature") is None


async def test_sensor_unavailable(hass):
    """Test when target sensor is Unavailable."""
    hass.states.async_set("sensor.unavailable", STATE_UNAVAILABLE)
    assert await async_setup_component(
        hass,
        "climate",
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "unavailable",
                "heater": ENT_SWITCH,
                "target_sensor": "sensor.unavailable",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.unavailable")
    assert state.attributes.get("current_temperature") is None


async def test_set_target_temp_heater_on(hass, setup_comp_2):
    """Test if target temperature turn heater on."""
    calls = _setup_switch(hass, False)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 30)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_set_target_temp_heater_off(hass, setup_comp_2):
    """Test if target temperature turn heater off."""
    calls = _setup_switch(hass, True)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 25)
    assert len(calls) == 2
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_heater_on_within_tolerance(hass, setup_comp_2):
    """Test if temperature change doesn't turn on within tolerance."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 29)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_heater_on_outside_tolerance(hass, setup_comp_2):
    """Test if temperature change turn heater on outside cold tolerance."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 27)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_heater_off_within_tolerance(hass, setup_comp_2):
    """Test if temperature change doesn't turn off within tolerance."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 33)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_heater_off_outside_tolerance(hass, setup_comp_2):
    """Test if temperature change turn heater off outside hot tolerance."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 35)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_running_when_hvac_mode_is_off(hass, setup_comp_2):
    """Test that the switch turns off when enabled is set False."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_no_state_change_when_hvac_mode_off(hass, setup_comp_2):
    """Test that the switch doesn't turn on when enabled is False."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_hvac_mode_heat(hass, setup_comp_2):
    """Test change mode from OFF to HEAT.

    Switch turns on when temp below setpoint and mode changes.
    """
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    calls = _setup_switch(hass, False)
    await common.async_set_hvac_mode(hass, HVAC_MODE_HEAT)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


def _setup_switch(hass, is_on):
    """Set up the test switch."""
    hass.states.async_set(ENT_SWITCH, STATE_ON if is_on else STATE_OFF)
    calls = []

    @callback
    def log_call(call):
        """Log service calls."""
        calls.append(call)

    hass.services.async_register(ha.DOMAIN, SERVICE_TURN_ON, log_call)
    hass.services.async_register(ha.DOMAIN, SERVICE_TURN_OFF, log_call)

    return calls


@pytest.fixture
async def setup_comp_3(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_CELSIUS
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 2,
                "hot_tolerance": 4,
                "away_temp": 30,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "ac_mode": True,
                "initial_hvac_mode": HVAC_MODE_COOL,
            }
        },
    )
    await hass.async_block_till_done()


async def test_set_target_temp_ac_off(hass, setup_comp_3):
    """Test if target temperature turn ac off."""
    calls = _setup_switch(hass, True)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 30)
    assert len(calls) == 2
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_turn_away_mode_on_cooling(hass, setup_comp_3):
    """Test the setting away mode when cooling."""
    _setup_switch(hass, True)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 19)
    await common.async_set_preset_mode(hass, PRESET_AWAY)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == 30


async def test_hvac_mode_cool(hass, setup_comp_3):
    """Test change mode from OFF to COOL.

    Switch turns on when temp below setpoint and mode changes.
    """
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    calls = _setup_switch(hass, False)
    await common.async_set_hvac_mode(hass, HVAC_MODE_COOL)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_set_target_temp_ac_on(hass, setup_comp_3):
    """Test if target temperature turn ac on."""
    calls = _setup_switch(hass, False)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 25)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_ac_off_within_tolerance(hass, setup_comp_3):
    """Test if temperature change doesn't turn ac off within tolerance."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 29.8)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_set_temp_change_ac_off_outside_tolerance(hass, setup_comp_3):
    """Test if temperature change turn ac off."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 27)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_ac_on_within_tolerance(hass, setup_comp_3):
    """Test if temperature change doesn't turn ac on within tolerance."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 25.2)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_ac_on_outside_tolerance(hass, setup_comp_3):
    """Test if temperature change turn ac on."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_running_when_operating_mode_is_off_2(hass, setup_comp_3):
    """Test that the switch turns off when enabled is set False."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_no_state_change_when_operation_mode_off_2(hass, setup_comp_3):
    """Test that the switch doesn't turn on when enabled is False."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    _setup_sensor(hass, 35)
    await hass.async_block_till_done()
    assert len(calls) == 0


@pytest.fixture
async def setup_comp_4(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_CELSIUS
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 0.3,
                "hot_tolerance": 0.3,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "ac_mode": True,
                "min_cycle_duration": datetime.timedelta(minutes=10),
                "initial_hvac_mode": HVAC_MODE_COOL,
            }
        },
    )
    await hass.async_block_till_done()


async def test_temp_change_ac_trigger_on_not_long_enough(hass, setup_comp_4):
    """Test if temperature change turn ac on."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_ac_trigger_on_long_enough(hass, setup_comp_4):
    """Test if temperature change turn ac on."""
    fake_changed = datetime.datetime(1918, 11, 11, 11, 11, 11, tzinfo=dt_util.UTC)
    with patch(
        "homeassistant.helpers.condition.dt_util.utcnow", return_value=fake_changed
    ):
        calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_ac_trigger_off_not_long_enough(hass, setup_comp_4):
    """Test if temperature change turn ac on."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_ac_trigger_off_long_enough(hass, setup_comp_4):
    """Test if temperature change turn ac on."""
    fake_changed = datetime.datetime(1918, 11, 11, 11, 11, 11, tzinfo=dt_util.UTC)
    with patch(
        "homeassistant.helpers.condition.dt_util.utcnow", return_value=fake_changed
    ):
        calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_mode_change_ac_trigger_off_not_long_enough(hass, setup_comp_4):
    """Test if mode change turns ac off despite minimum cycle."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "homeassistant"
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_mode_change_ac_trigger_on_not_long_enough(hass, setup_comp_4):
    """Test if mode change turns ac on despite minimum cycle."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 0
    await common.async_set_hvac_mode(hass, HVAC_MODE_HEAT)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "homeassistant"
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


@pytest.fixture
async def setup_comp_5(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_CELSIUS
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 0.3,
                "hot_tolerance": 0.3,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "ac_mode": True,
                "min_cycle_duration": datetime.timedelta(minutes=10),
                "initial_hvac_mode": HVAC_MODE_COOL,
            }
        },
    )
    await hass.async_block_till_done()


async def test_temp_change_ac_trigger_on_not_long_enough_2(hass, setup_comp_5):
    """Test if temperature change turn ac on."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_ac_trigger_on_long_enough_2(hass, setup_comp_5):
    """Test if temperature change turn ac on."""
    fake_changed = datetime.datetime(1918, 11, 11, 11, 11, 11, tzinfo=dt_util.UTC)
    with patch(
        "homeassistant.helpers.condition.dt_util.utcnow", return_value=fake_changed
    ):
        calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_ac_trigger_off_not_long_enough_2(hass, setup_comp_5):
    """Test if temperature change turn ac on."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_ac_trigger_off_long_enough_2(hass, setup_comp_5):
    """Test if temperature change turn ac on."""
    fake_changed = datetime.datetime(1918, 11, 11, 11, 11, 11, tzinfo=dt_util.UTC)
    with patch(
        "homeassistant.helpers.condition.dt_util.utcnow", return_value=fake_changed
    ):
        calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_mode_change_ac_trigger_off_not_long_enough_2(hass, setup_comp_5):
    """Test if mode change turns ac off despite minimum cycle."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "homeassistant"
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_mode_change_ac_trigger_on_not_long_enough_2(hass, setup_comp_5):
    """Test if mode change turns ac on despite minimum cycle."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 0
    await common.async_set_hvac_mode(hass, HVAC_MODE_HEAT)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "homeassistant"
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


@pytest.fixture
async def setup_comp_6(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_CELSIUS
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 0.3,
                "hot_tolerance": 0.3,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "min_cycle_duration": datetime.timedelta(minutes=10),
                "initial_hvac_mode": HVAC_MODE_HEAT,
            }
        },
    )
    await hass.async_block_till_done()


async def test_temp_change_heater_trigger_off_not_long_enough(hass, setup_comp_6):
    """Test if temp change doesn't turn heater off because of time."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_heater_trigger_on_not_long_enough(hass, setup_comp_6):
    """Test if temp change doesn't turn heater on because of time."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_temp_change_heater_trigger_on_long_enough(hass, setup_comp_6):
    """Test if temperature change turn heater on after min cycle."""
    fake_changed = datetime.datetime(1918, 11, 11, 11, 11, 11, tzinfo=dt_util.UTC)
    with patch(
        "homeassistant.helpers.condition.dt_util.utcnow", return_value=fake_changed
    ):
        calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_heater_trigger_off_long_enough(hass, setup_comp_6):
    """Test if temperature change turn heater off after min cycle."""
    fake_changed = datetime.datetime(1918, 11, 11, 11, 11, 11, tzinfo=dt_util.UTC)
    with patch(
        "homeassistant.helpers.condition.dt_util.utcnow", return_value=fake_changed
    ):
        calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_mode_change_heater_trigger_off_not_long_enough(hass, setup_comp_6):
    """Test if mode change turns heater off despite minimum cycle."""
    calls = _setup_switch(hass, True)
    await common.async_set_temperature(hass, 25)
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    assert len(calls) == 0
    await common.async_set_hvac_mode(hass, HVAC_MODE_OFF)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "homeassistant"
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_mode_change_heater_trigger_on_not_long_enough(hass, setup_comp_6):
    """Test if mode change turns heater on despite minimum cycle."""
    calls = _setup_switch(hass, False)
    await common.async_set_temperature(hass, 30)
    _setup_sensor(hass, 25)
    await hass.async_block_till_done()
    assert len(calls) == 0
    await common.async_set_hvac_mode(hass, HVAC_MODE_HEAT)
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == "homeassistant"
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


@pytest.fixture
async def setup_comp_7(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_CELSIUS
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 0.3,
                "hot_tolerance": 0.3,
                "heater": ENT_SWITCH,
                "target_temp": 25,
                "target_sensor": ENT_SENSOR,
                "ac_mode": True,
                "min_cycle_duration": datetime.timedelta(minutes=15),
                "keep_alive": datetime.timedelta(minutes=10),
                "initial_hvac_mode": HVAC_MODE_COOL,
            }
        },
    )

    await hass.async_block_till_done()


async def test_temp_change_ac_trigger_on_long_enough_3(hass, setup_comp_7):
    """Test if turn on signal is sent at keep-alive intervals."""
    calls = _setup_switch(hass, True)
    await hass.async_block_till_done()
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 25)
    test_time = datetime.datetime.now(dt_util.UTC)
    async_fire_time_changed(hass, test_time)
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=5))
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=10))
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_ac_trigger_off_long_enough_3(hass, setup_comp_7):
    """Test if turn on signal is sent at keep-alive intervals."""
    calls = _setup_switch(hass, False)
    await hass.async_block_till_done()
    _setup_sensor(hass, 20)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 25)
    test_time = datetime.datetime.now(dt_util.UTC)
    async_fire_time_changed(hass, test_time)
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=5))
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=10))
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


@pytest.fixture
async def setup_comp_8(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_CELSIUS
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 0.3,
                "hot_tolerance": 0.3,
                "target_temp": 25,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "min_cycle_duration": datetime.timedelta(minutes=15),
                "keep_alive": datetime.timedelta(minutes=10),
                "initial_hvac_mode": HVAC_MODE_HEAT,
            }
        },
    )
    await hass.async_block_till_done()


async def test_temp_change_heater_trigger_on_long_enough_2(hass, setup_comp_8):
    """Test if turn on signal is sent at keep-alive intervals."""
    calls = _setup_switch(hass, True)
    await hass.async_block_till_done()
    _setup_sensor(hass, 20)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 25)
    test_time = datetime.datetime.now(dt_util.UTC)
    async_fire_time_changed(hass, test_time)
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=5))
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=10))
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_ON
    assert call.data["entity_id"] == ENT_SWITCH


async def test_temp_change_heater_trigger_off_long_enough_2(hass, setup_comp_8):
    """Test if turn on signal is sent at keep-alive intervals."""
    calls = _setup_switch(hass, False)
    await hass.async_block_till_done()
    _setup_sensor(hass, 30)
    await hass.async_block_till_done()
    await common.async_set_temperature(hass, 25)
    test_time = datetime.datetime.now(dt_util.UTC)
    async_fire_time_changed(hass, test_time)
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=5))
    await hass.async_block_till_done()
    assert len(calls) == 0
    async_fire_time_changed(hass, test_time + datetime.timedelta(minutes=10))
    await hass.async_block_till_done()
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


@pytest.fixture
async def setup_comp_9(hass):
    """Initialize components."""
    hass.config.temperature_unit = TEMP_FAHRENHEIT
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 0.3,
                "hot_tolerance": 0.3,
                "target_temp": 25,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "min_cycle_duration": datetime.timedelta(minutes=15),
                "keep_alive": datetime.timedelta(minutes=10),
                "precision": 0.1,
            }
        },
    )
    await hass.async_block_till_done()


async def test_precision(hass, setup_comp_9):
    """Test that setting precision to tenths works as intended."""
    await common.async_set_temperature(hass, 23.27)
    state = hass.states.get(ENTITY)
    assert state.attributes.get("temperature") == 23.3


async def test_custom_setup_params(hass):
    """Test the setup with custom parameters."""
    result = await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "min_temp": MIN_TEMP,
                "max_temp": MAX_TEMP,
                "target_temp": TARGET_TEMP,
            }
        },
    )
    assert result
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.attributes.get("min_temp") == MIN_TEMP
    assert state.attributes.get("max_temp") == MAX_TEMP
    assert state.attributes.get("temperature") == TARGET_TEMP


@pytest.mark.parametrize("hvac_mode", [HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL])
async def test_restore_state(hass, hvac_mode):
    """Ensure states are restored on startup."""
    mock_restore_cache(
        hass,
        (
            State(
                "climate.test_thermostat",
                hvac_mode,
                {ATTR_TEMPERATURE: "20", ATTR_PRESET_MODE: PRESET_AWAY},
            ),
        ),
    )

    hass.state = CoreState.starting

    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test_thermostat",
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "away_temp": 14,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.test_thermostat")
    assert state.attributes[ATTR_TEMPERATURE] == 20
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_AWAY
    assert state.state == hvac_mode


async def test_no_restore_state(hass):
    """Ensure states are restored on startup if they exist.

    Allows for graceful reboot.
    """
    mock_restore_cache(
        hass,
        (
            State(
                "climate.test_thermostat",
                HVAC_MODE_OFF,
                {ATTR_TEMPERATURE: "20", ATTR_PRESET_MODE: PRESET_AWAY},
            ),
        ),
    )

    hass.state = CoreState.starting

    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test_thermostat",
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "target_temp": 22,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.test_thermostat")
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert state.state == HVAC_MODE_OFF


async def test_initial_hvac_off_force_heater_off(hass):
    """Ensure that restored state is coherent with real situation.

    'initial_hvac_mode: off' will force HVAC status, but we must be sure
    that heater don't keep on.
    """
    # switch is on
    calls = _setup_switch(hass, True)
    assert hass.states.get(ENT_SWITCH).state == STATE_ON

    _setup_sensor(hass, 16)

    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test_thermostat",
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "target_temp": 20,
                "initial_hvac_mode": HVAC_MODE_OFF,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.test_thermostat")
    # 'initial_hvac_mode' will force state but must prevent heather keep working
    assert state.state == HVAC_MODE_OFF
    # heater must be switched off
    assert len(calls) == 1
    call = calls[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == ENT_SWITCH


async def test_restore_will_turn_off_(hass):
    """Ensure that restored state is coherent with real situation.

    Thermostat status must trigger heater event if temp raises the target .
    """
    heater_switch = "input_boolean.test"
    mock_restore_cache(
        hass,
        (
            State(
                "climate.test_thermostat",
                HVAC_MODE_HEAT,
                {ATTR_TEMPERATURE: "18", ATTR_PRESET_MODE: PRESET_NONE},
            ),
            State(heater_switch, STATE_ON, {}),
        ),
    )

    hass.state = CoreState.starting

    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    await hass.async_block_till_done()
    assert hass.states.get(heater_switch).state == STATE_ON

    _setup_sensor(hass, 22)

    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test_thermostat",
                "heater": heater_switch,
                "target_sensor": ENT_SENSOR,
                "target_temp": 20,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.test_thermostat")
    assert state.attributes[ATTR_TEMPERATURE] == 20
    assert state.state == HVAC_MODE_HEAT
    assert hass.states.get(heater_switch).state == STATE_ON


async def test_restore_will_turn_off_when_loaded_second(hass):
    """Ensure that restored state is coherent with real situation.

    Switch is not available until after component is loaded
    """
    heater_switch = "input_boolean.test"
    mock_restore_cache(
        hass,
        (
            State(
                "climate.test_thermostat",
                HVAC_MODE_HEAT,
                {ATTR_TEMPERATURE: "18", ATTR_PRESET_MODE: PRESET_NONE},
            ),
            State(heater_switch, STATE_ON, {}),
        ),
    )

    hass.state = CoreState.starting

    await hass.async_block_till_done()
    assert hass.states.get(heater_switch) is None

    _setup_sensor(hass, 16)

    await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test_thermostat",
                "heater": heater_switch,
                "target_sensor": ENT_SENSOR,
                "target_temp": 20,
                "initial_hvac_mode": HVAC_MODE_OFF,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("climate.test_thermostat")
    assert state.attributes[ATTR_TEMPERATURE] == 20
    assert state.state == HVAC_MODE_OFF

    calls_on = async_mock_service(hass, ha.DOMAIN, SERVICE_TURN_ON)
    calls_off = async_mock_service(hass, ha.DOMAIN, SERVICE_TURN_OFF)

    assert await async_setup_component(
        hass, input_boolean.DOMAIN, {"input_boolean": {"test": None}}
    )
    await hass.async_block_till_done()
    # heater must be switched off
    assert len(calls_on) == 0
    assert len(calls_off) == 1
    call = calls_off[0]
    assert call.domain == HASS_DOMAIN
    assert call.service == SERVICE_TURN_OFF
    assert call.data["entity_id"] == "input_boolean.test"


async def test_restore_state_incoherence_case(hass):
    """
    Test restore from a strange state.

    - Turn the generic thermostat off
    - Restart HA and restore state from DB
    """
    _mock_restore_cache(hass, temperature=20)

    calls = _setup_switch(hass, False)
    _setup_sensor(hass, 15)
    await _setup_climate(hass)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY)
    assert state.attributes[ATTR_TEMPERATURE] == 20
    assert state.state == HVAC_MODE_OFF
    assert len(calls) == 0

    calls = _setup_switch(hass, False)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state.state == HVAC_MODE_OFF


async def _setup_climate(hass):
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "cold_tolerance": 2,
                "hot_tolerance": 4,
                "away_temp": 30,
                "heater": ENT_SWITCH,
                "target_sensor": ENT_SENSOR,
                "ac_mode": True,
            }
        },
    )


def _mock_restore_cache(hass, temperature=20, hvac_mode=HVAC_MODE_OFF):
    mock_restore_cache(
        hass,
        (
            State(
                ENTITY,
                hvac_mode,
                {ATTR_TEMPERATURE: str(temperature), ATTR_PRESET_MODE: PRESET_AWAY},
            ),
        ),
    )


async def test_reload(hass):
    """Test we can reload."""

    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "climate": {
                "platform": "generic_thermostat",
                "name": "test",
                "heater": "switch.any",
                "target_sensor": "sensor.any",
            }
        },
    )

    await hass.async_block_till_done()
    assert len(hass.states.async_all()) == 1
    assert hass.states.get("climate.test") is not None

    yaml_path = get_fixture_path("configuration.yaml", "generic_thermostat")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(
            GENERIC_THERMOSTAT_DOMAIN,
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 1
    assert hass.states.get("climate.test") is None
    assert hass.states.get("climate.reload")
