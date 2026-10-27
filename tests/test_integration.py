"""Setup, the check service and the dwell trigger end to end, with Places mocked."""

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.store_lists.const import DOMAIN, EVENT_MATCH, PLACES_URL

IKEA = {
    "places": [
        {
            "id": "ikea0001loures",
            "displayName": {"text": "IKEA Loures"},
            "primaryType": "furniture_store",
        }
    ]
}
LISTS = [
    {"todo": "todo.casa", "kind": "home", "keywords": ""},
    {"todo": "todo.construcao", "kind": "diy", "keywords": ""},
]
AWAY = {"latitude": 38.8174, "longitude": -9.1481, "gps_accuracy": 10}


@pytest.fixture
def notified(hass: HomeAssistant) -> list[ServiceCall]:
    """A phone for person.lucas: a mobile_app tracker on a device whose notify service exists."""
    owner = MockConfigEntry(domain="mobile_app")
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("mobile_app", "phone")}, name="Lucas iPhone"
    )
    er.async_get(hass).async_get_or_create(
        "device_tracker",
        "mobile_app",
        "phone",
        device_id=device.id,
        suggested_object_id="lucas_iphone",
    )
    return async_mock_service(hass, "notify", "mobile_app_lucas_iphone")


@pytest.fixture
def todo_items(hass: HomeAssistant) -> None:
    async def get_items(call: ServiceCall):
        return {
            e: {"items": [{"summary": "Lâmpadas"}, {"summary": "Cabides"}]}
            for e in call.data["entity_id"]
        }

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("todo.casa", "2", {"friendly_name": "Casa"})
    hass.states.async_set("todo.construcao", "0", {"friendly_name": "Construção"})


@pytest.fixture
async def entry(hass: HomeAssistant, notified, todo_items) -> MockConfigEntry:
    hass.states.async_set(
        "person.lucas",
        "home",
        {"latitude": 39.1, "longitude": -9.3, "device_trackers": ["device_tracker.lucas_iphone"]},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={"api_key": "k"},
        options={
            "people": ["person.lucas"],
            "lists": LISTS,
            "start": "00:00:00",
            "end": "23:59:00",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_checks_the_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(PLACES_URL, status=403, json={"error": {"message": "blocked"}})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "bad"})
    assert result["errors"] == {"base": "invalid_key"}

    aioclient_mock.clear_requests()
    aioclient_mock.post(PLACES_URL, json={})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "good"})
    assert result["step_id"] == "people"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"people": ["person.lucas"]}
    )
    assert result["type"] == "create_entry"
    assert result["data"] == {"api_key": "good"}
    assert result["options"]["lists"] == []


async def test_options_add_and_remove_a_list(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "list_add"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"todo": "todo.shopping", "kind": "mall"}
    )
    assert [i["todo"] for i in entry.options["lists"]] == [
        "todo.casa",
        "todo.construcao",
        "todo.shopping",
    ]
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "list_remove"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"lists": ["todo.construcao"]}
    )
    assert [i["todo"] for i in entry.options["lists"]] == ["todo.casa", "todo.shopping"]


async def test_check_service_answers_without_notifying(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, notified
) -> None:
    aioclient_mock.post(PLACES_URL, json=IKEA)
    result = await hass.services.async_call(
        DOMAIN,
        "check",
        {"person": "person.lucas", "latitude": 38.8, "longitude": -9.1},
        blocking=True,
        return_response=True,
    )
    assert result["place"] == "IKEA Loures"
    assert result["lists"] == ["todo.casa"]
    assert result["message"] == "Casa: Lâmpadas, Cabides"
    assert notified == []


async def test_stopping_at_a_shop_notifies_once_a_day(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, notified
) -> None:
    aioclient_mock.post(PLACES_URL, json=IKEA)
    matches = async_capture_events(hass, EVENT_MATCH)
    hass.states.async_set(
        "person.lucas", "not_home", {**AWAY, "device_trackers": ["device_tracker.lucas_iphone"]}
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=4))
    await hass.async_block_till_done()

    assert len(notified) == 1
    call = notified[0].data
    assert call["title"] == "🛒 IKEA Loures"
    assert call["message"] == "Casa: Lâmpadas, Cabides"
    assert call["data"]["actions"][0]["uri"] == "/todo?entity_id=todo.casa"
    assert len(matches) == 1
    assert [s.state for s in hass.states.async_all("sensor")] == ["IKEA Loures"]

    # Back from lunch next door: same shop, same day, no second notification.
    hass.states.async_set(
        "person.lucas",
        "not_home",
        {**AWAY, "latitude": 38.8175, "device_trackers": ["device_tracker.lucas_iphone"]},
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
    await hass.async_block_till_done()
    assert len(notified) == 1


async def test_moving_again_before_the_dwell_cancels_the_look(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, notified
) -> None:
    aioclient_mock.post(PLACES_URL, json=IKEA)
    hass.states.async_set(
        "person.lucas", "not_home", {**AWAY, "device_trackers": ["device_tracker.lucas_iphone"]}
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    hass.states.async_set(
        "person.lucas",
        "home",
        {"latitude": 39.1, "longitude": -9.3, "device_trackers": ["device_tracker.lucas_iphone"]},
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0
    assert notified == []


async def test_places_error_raises_an_issue_and_tells_once(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker, notified
) -> None:
    aioclient_mock.post(PLACES_URL, status=403, json={"error": {"message": "API key blocked"}})
    for _ in range(2):
        result = await hass.services.async_call(
            DOMAIN,
            "check",
            {"person": "person.lucas", "latitude": 38.8, "longitude": -9.1},
            blocking=True,
            return_response=True,
        )
    assert "API key blocked" in result["error"]
    from homeassistant.helpers import issue_registry as ir

    assert ir.async_get(hass).async_get_issue(DOMAIN, "places_error") is not None
    assert len(notified) == 1
