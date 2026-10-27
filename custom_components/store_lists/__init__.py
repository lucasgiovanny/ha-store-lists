"""Store Lists: the right shopping list on your phone when you stop at a shop that serves it."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SERVICE_CHECK
from .watcher import StoreWatcher

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type StoreListsConfigEntry = ConfigEntry[StoreWatcher]

CHECK_SCHEMA = vol.Schema(
    {
        vol.Required("person"): cv.entity_id,
        vol.Inclusive("latitude", "point"): cv.latitude,
        vol.Inclusive("longitude", "point"): cv.longitude,
        vol.Optional("notify", default=False): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def check(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
        watcher: StoreWatcher = entries[0].runtime_data
        return await watcher.async_check(
            call.data["person"],
            call.data.get("latitude"),
            call.data.get("longitude"),
            notify=call.data["notify"],
            force=True,
        )

    hass.services.async_register(
        DOMAIN, SERVICE_CHECK, check, schema=CHECK_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: StoreListsConfigEntry) -> bool:
    watcher = StoreWatcher(hass, entry.entry_id, {**entry.data, **entry.options})
    await watcher.async_load()
    entry.runtime_data = watcher
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    watcher.async_start()
    entry.async_on_unload(watcher.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StoreListsConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: StoreListsConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
