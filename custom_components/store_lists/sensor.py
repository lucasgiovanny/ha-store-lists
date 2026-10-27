"""One sensor per person: the last shop they stopped at and the lists it served."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import StoreListsConfigEntry
from .const import DOMAIN, SIGNAL_UPDATE
from .watcher import StoreWatcher


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StoreListsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        LastStoreSensor(entry.runtime_data, person) for person in entry.runtime_data.people
    )


class LastStoreSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:store-marker"
    _attr_translation_key = "last_store"

    def __init__(self, watcher: StoreWatcher, person: str) -> None:
        self._watcher = watcher
        self._person = person
        state = watcher.hass.states.get(person)
        name = state.name if state else person.split(".", 1)[1]
        self._attr_unique_id = f"{watcher.entry_id}_{person}"
        self._attr_translation_placeholders = {"person": name}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, watcher.entry_id)},
            name="Store Lists",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{SIGNAL_UPDATE}_{self._watcher.entry_id}", self._updated
            )
        )

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        return self._watcher.last.get(self._person, {}).get("place")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._watcher.last.get(self._person, {})
        return {"person": self._person, "lists": last.get("lists", []), "at": last.get("at")}
