"""Set up with a Google Places key and the people to watch; lists and timing live in the options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_DWELL,
    CONF_END,
    CONF_ERRORS_TO,
    CONF_KEYWORDS,
    CONF_KIND,
    CONF_LISTS,
    CONF_PEOPLE,
    CONF_RADIUS,
    CONF_START,
    CONF_TODO,
    DEFAULT_DWELL,
    DEFAULT_END,
    DEFAULT_RADIUS,
    DEFAULT_START,
    DOMAIN,
    KINDS,
)
from .places import PlacesError, search_nearby

PERSON = selector.EntitySelector(selector.EntitySelectorConfig(domain="person"))
PEOPLE = selector.EntitySelector(selector.EntitySelectorConfig(domain="person", multiple=True))


def _people_schema(opts: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_PEOPLE, default=opts.get(CONF_PEOPLE, [])): PEOPLE,
            vol.Optional(
                CONF_ERRORS_TO, description={"suggested_value": opts.get(CONF_ERRORS_TO)}
            ): PERSON,
        }
    )


class StoreListsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._key = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> StoreListsOptionsFlow:
        return StoreListsOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await search_nearby(
                    async_get_clientsession(self.hass),
                    user_input[CONF_API_KEY],
                    self.hass.config.latitude,
                    self.hass.config.longitude,
                    50,
                    max_results=1,
                )
            except PlacesError as err:
                errors["base"] = "cannot_connect" if err.status is None else "invalid_key"
            else:
                self._key = user_input[CONF_API_KEY]
                return await self.async_step_people()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_people(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Store Lists",
                data={CONF_API_KEY: self._key},
                options={
                    CONF_PEOPLE: user_input[CONF_PEOPLE],
                    CONF_ERRORS_TO: user_input.get(CONF_ERRORS_TO),
                    CONF_LISTS: [],
                },
            )
        return self.async_show_form(step_id="people", data_schema=_people_schema({}))


class StoreListsOptionsFlow(OptionsFlow):
    @property
    def _opts(self) -> dict[str, Any]:
        return dict(self.config_entry.options)

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self._opts, **changes})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["list_add", "list_remove", "people", "settings"]
        )

    async def async_step_list_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        lists = self._opts.get(CONF_LISTS, [])
        if user_input is not None:
            item = {
                CONF_TODO: user_input[CONF_TODO],
                CONF_KIND: user_input[CONF_KIND],
                CONF_KEYWORDS: user_input.get(CONF_KEYWORDS, "").strip(),
            }
            others = [i for i in lists if i[CONF_TODO] != item[CONF_TODO]]
            return self._save(**{CONF_LISTS: [*others, item]})
        return self.async_show_form(
            step_id="list_add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TODO): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="todo")
                    ),
                    vol.Required(CONF_KIND): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=KINDS, translation_key="kind")
                    ),
                    vol.Optional(CONF_KEYWORDS): str,
                }
            ),
        )

    async def async_step_list_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        lists = self._opts.get(CONF_LISTS, [])
        if user_input is not None:
            gone = set(user_input[CONF_LISTS])
            return self._save(**{CONF_LISTS: [i for i in lists if i[CONF_TODO] not in gone]})
        options = [
            selector.SelectOptionDict(
                value=i[CONF_TODO],
                label=(s.name if (s := self.hass.states.get(i[CONF_TODO])) else i[CONF_TODO]),
            )
            for i in lists
        ]
        return self.async_show_form(
            step_id="list_remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LISTS): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
        )

    async def async_step_people(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                **{
                    CONF_PEOPLE: user_input[CONF_PEOPLE],
                    CONF_ERRORS_TO: user_input.get(CONF_ERRORS_TO),
                }
            )
        return self.async_show_form(step_id="people", data_schema=_people_schema(self._opts))

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        opts = self._opts
        if user_input is not None:
            return self._save(
                **{
                    CONF_RADIUS: int(user_input[CONF_RADIUS]),
                    CONF_DWELL: int(user_input[CONF_DWELL]),
                    CONF_START: user_input[CONF_START],
                    CONF_END: user_input[CONF_END],
                }
            )
        box = selector.NumberSelectorMode.BOX
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RADIUS, default=opts.get(CONF_RADIUS, DEFAULT_RADIUS)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=30, max=500, step=10, mode=box, unit_of_measurement="m"
                        )
                    ),
                    vol.Required(
                        CONF_DWELL, default=opts.get(CONF_DWELL, DEFAULT_DWELL)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=30, mode=box, unit_of_measurement="min"
                        )
                    ),
                    vol.Required(
                        CONF_START, default=opts.get(CONF_START, DEFAULT_START)
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_END, default=opts.get(CONF_END, DEFAULT_END)
                    ): selector.TimeSelector(),
                }
            ),
        )
