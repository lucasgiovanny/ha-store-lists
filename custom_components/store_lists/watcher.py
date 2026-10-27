"""Watches people: after a few minutes still away from home, asks Places what shop they are at."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Any

from homeassistant.const import STATE_HOME
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_API_KEY,
    CONF_DWELL,
    CONF_END,
    CONF_ERRORS_TO,
    CONF_LISTS,
    CONF_PEOPLE,
    CONF_RADIUS,
    CONF_START,
    DEFAULT_DWELL,
    DEFAULT_END,
    DEFAULT_RADIUS,
    DEFAULT_START,
    DOMAIN,
    EVENT_MATCH,
    MALL_RADIUS,
    MAX_ACCURACY,
    SEARCH_TYPES,
    SIGNAL_UPDATE,
    STORAGE_VERSION,
)
from .logic import classify, lists_for, message, wants_mall_name
from .places import PlacesError, search_nearby

_LOGGER = logging.getLogger(__name__)


def _time(value: str) -> tuple[int, int]:
    parts = [int(p) for p in str(value).split(":")[:2]]
    return parts[0], parts[1] if len(parts) > 1 else 0


class StoreWatcher:
    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict[str, Any]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.api_key: str = config[CONF_API_KEY]
        self.people: list[str] = config.get(CONF_PEOPLE, [])
        self.lists: list[dict[str, Any]] = config.get(CONF_LISTS, [])
        self.radius = float(config.get(CONF_RADIUS, DEFAULT_RADIUS))
        self.dwell = float(config.get(CONF_DWELL, DEFAULT_DWELL)) * 60
        self.start = _time(config.get(CONF_START, DEFAULT_START))
        self.end = _time(config.get(CONF_END, DEFAULT_END))
        self.errors_to: str | None = config.get(CONF_ERRORS_TO) or (
            self.people[0] if self.people else None
        )
        self.last: dict[str, dict[str, Any]] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._day = ""
        self._seen: list[str] = []
        self._timers: dict[str, CALLBACK_TYPE] = {}
        self._unsub: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._day, self._seen = data.get("day", ""), data.get("seen", [])
        self.last = data.get("last", {})

    @callback
    def async_start(self) -> None:
        if self.people:
            self._unsub.append(async_track_state_change_event(self.hass, self.people, self._moved))

    @callback
    def async_stop(self) -> None:
        for unsub in [*self._unsub, *self._timers.values()]:
            unsub()
        self._unsub, self._timers = [], {}

    def _save(self) -> None:
        self._store.async_delay_save(
            lambda: {"day": self._day, "seen": self._seen, "last": self.last}, 5
        )

    def _seen_today(self) -> list[str]:
        today = dt_util.now().date().isoformat()
        if self._day != today:
            self._day, self._seen = today, []
        return self._seen

    @callback
    def _moved(self, event: Event[EventStateChangedData]) -> None:
        new, old = event.data["new_state"], event.data["old_state"]
        if new is None:
            return
        here = (new.attributes.get("latitude"), new.attributes.get("longitude"))
        if here[0] is None or (
            old and here == (old.attributes.get("latitude"), old.attributes.get("longitude"))
        ):
            return
        person = new.entity_id
        if cancel := self._timers.pop(person, None):
            cancel()
        # The phone only reports when it moves, so a quiet spell means the person stopped there.
        self._timers[person] = async_call_later(
            self.hass, self.dwell, partial(self._dwelled, person)
        )

    async def _dwelled(self, person: str, _now: datetime) -> None:
        self._timers.pop(person, None)
        await self.async_check(person)

    def _open(self) -> bool:
        now = dt_util.now()
        minutes = now.hour * 60 + now.minute
        return self.start[0] * 60 + self.start[1] <= minutes < self.end[0] * 60 + self.end[1]

    def _counts(self) -> dict[str, int]:
        counts = {}
        for item in self.lists:
            state = self.hass.states.get(item["todo"])
            try:
                counts[item["todo"]] = int(state.state) if state else 0
            except ValueError:
                counts[item["todo"]] = 0
        return counts

    async def async_check(
        self,
        person: str,
        latitude: float | None = None,
        longitude: float | None = None,
        *,
        notify: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        """Look around a person (or a given point) and tell them which lists this shop is for."""
        state = self.hass.states.get(person)
        # Only where the person really is counts as their last shop; a point to test does not.
        real = latitude is None or longitude is None
        if latitude is None or longitude is None:
            if state is None or state.attributes.get("latitude") is None:
                return {"skipped": "no_location"}
            latitude, longitude = state.attributes["latitude"], state.attributes["longitude"]
            if not force:
                if state.state == STATE_HOME:
                    return {"skipped": "home"}
                if float(state.attributes.get("gps_accuracy") or 0) > MAX_ACCURACY:
                    return {"skipped": "inaccurate"}
        if not force and not self._open():
            return {"skipped": "hours"}
        counts = self._counts()
        if not force and not any(counts.values()):
            return {"skipped": "empty_lists"}

        session = async_get_clientsession(self.hass)
        language = self.hass.config.language or "en"
        try:
            places = await search_nearby(
                session,
                self.api_key,
                latitude,
                longitude,
                self.radius,
                types=SEARCH_TYPES,
                language=language,
            )
            found = classify(places, self.lists)
            if wants_mall_name(found):
                # Shops inside malls are often tagged as malls themselves: the busiest one nearby is the real one.
                malls = await search_nearby(
                    session,
                    self.api_key,
                    latitude,
                    longitude,
                    MALL_RADIUS,
                    primary_types=["shopping_mall"],
                    rank="POPULARITY",
                    max_results=1,
                    language=language,
                )
                if malls:
                    found.mall = malls[0]
        except PlacesError as err:
            await self._failed(err)
            return {"error": str(err)}
        ir.async_delete_issue(self.hass, DOMAIN, "places_error")

        todos = lists_for(found, self.lists, counts)
        where = found.where
        result: dict[str, Any] = {
            "place": where.name if where else None,
            "mall": found.mall.name if found.mall else None,
            "lists": todos,
            "shops": {todo: [p.name for p in shops] for todo, shops in found.shops.items()},
            "nearby": [p.name for p in places],
        }
        if where and real:
            self.last[person] = {
                "place": where.name,
                "lists": todos,
                "at": dt_util.now().isoformat(),
            }
            async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry_id}")
            self._save()
        if not todos or where is None:
            return result
        key = f"{person}:{where.id}"
        if key in self._seen_today() and not force:
            return {**result, "skipped": "already_told"}

        items = await self._items(todos)
        names = {t: (s.name if (s := self.hass.states.get(t)) else t) for t in todos}
        text = message(found, todos, names, items)
        result["message"] = text
        if notify:
            await self._notify(person, f"🛒 {where.name}", text, todos, names, where.id)
            self._seen.append(key)
            self._save()
        self.hass.bus.async_fire(EVENT_MATCH, {"person": person, **result})
        return result

    async def _items(self, todos: list[str]) -> dict[str, list[str]]:
        resp = await self.hass.services.async_call(
            "todo",
            "get_items",
            {"entity_id": todos, "status": "needs_action"},
            blocking=True,
            return_response=True,
        )
        answer: dict[str, Any] = dict(resp or {})
        return {
            todo: [i["summary"] for i in answer.get(todo, {}).get("items", [])] for todo in todos
        }

    def notify_service(self, person: str) -> str | None:
        """The companion app's notify service for a person's phone, found through their trackers."""
        state = self.hass.states.get(person)
        ents, devs = er.async_get(self.hass), dr.async_get(self.hass)
        for tracker in state.attributes.get("device_trackers", []) if state else []:
            entity = ents.async_get(tracker)
            device = devs.async_get(entity.device_id) if entity and entity.device_id else None
            if entity is None or entity.platform != "mobile_app" or device is None:
                continue
            service = f"mobile_app_{slugify(device.name_by_user or device.name or '')}"
            if self.hass.services.has_service("notify", service):
                return service
        return None

    async def _notify(
        self, person: str, title: str, text: str, todos: list[str], names: dict[str, str], tag: str
    ) -> None:
        service = self.notify_service(person)
        if service is None:
            _LOGGER.warning("No companion app notify service found for %s", person)
            return
        data = {
            "tag": f"{DOMAIN}-{tag[-8:]}",
            "url": f"/todo?entity_id={todos[0]}",
            "actions": [
                {"action": "URI", "title": names[t], "uri": f"/todo?entity_id={t}"} for t in todos
            ],
        }
        await self.hass.services.async_call(
            "notify", service, {"title": title, "message": text, "data": data}, blocking=True
        )

    async def _failed(self, err: PlacesError) -> None:
        _LOGGER.warning("Google Places request failed: %s", err)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            "places_error",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="places_error",
            translation_placeholders={"error": str(err)},
        )
        seen = self._seen_today()
        if "error" in seen or not self.errors_to:
            return
        seen.append("error")
        self._save()
        if service := self.notify_service(self.errors_to):
            await self.hass.services.async_call(
                "notify",
                service,
                {"title": "🛒 Google Places", "message": str(err)[:200]},
                blocking=True,
            )
