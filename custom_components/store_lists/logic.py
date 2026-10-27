"""Pure rules: which shops a Places answer holds and which lists they are for."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .const import (
    DIY_BRANDS,
    DIY_TYPES,
    GENERAL_TYPES,
    HOME_BRANDS,
    HOME_TYPES,
    KIND_DIY,
    KIND_HOME,
    KIND_KEYWORDS,
    KIND_MALL,
    MALL_TYPES,
    MAX_ITEMS_SHOWN,
    MAX_SHOPS_SHOWN,
    NOT_HOME,
)


@dataclass
class Place:
    id: str
    name: str
    primary: str


@dataclass
class Found:
    """What is around: the mall (if any) and the shops matching each kind or keyword."""

    places: list[Place]
    mall: Place | None = None
    shops: dict[str, list[Place]] = field(default_factory=dict)

    @property
    def where(self) -> Place | None:
        """The place a visit is counted against: the mall, else the first matching shop."""
        if self.mall:
            return self.mall
        return next((p for shops in self.shops.values() for p in shops), None)


def parse_places(content: dict[str, Any] | None) -> list[Place]:
    return [
        Place(
            id=p.get("id", ""),
            name=(p.get("displayName") or {}).get("text", ""),
            primary=p.get("primaryType", ""),
        )
        for p in (content or {}).get("places", [])
    ]


def _search(pattern: str, name: str) -> bool:
    return bool(pattern) and re.search(pattern, name, re.IGNORECASE) is not None


def is_home(place: Place) -> bool:
    if _search(HOME_BRANDS, place.name):
        return True
    return (
        place.primary in HOME_TYPES
        and place.primary not in GENERAL_TYPES
        and not _search(NOT_HOME, place.name)
    )


def is_diy(place: Place) -> bool:
    return _search(DIY_BRANDS, place.name) or place.primary in DIY_TYPES


def keywords_pattern(keywords: str | None) -> str:
    words = [w.strip() for w in (keywords or "").split(",") if w.strip()]
    return "|".join(re.escape(w) for w in words)


def classify(places: list[Place], lists: list[dict[str, Any]]) -> Found:
    """Sort the shops into the configured lists; keywords add to whatever the kind matches."""
    found = Found(places=places)
    found.mall = next((p for p in places if p.primary in MALL_TYPES), None)
    for item in lists:
        kind, pattern = item["kind"], keywords_pattern(item.get("keywords"))
        rule = {KIND_HOME: is_home, KIND_DIY: is_diy}.get(kind)
        shops = [
            p
            for p in places
            if p.primary not in MALL_TYPES and ((rule and rule(p)) or _search(pattern, p.name))
        ]
        if shops:
            found.shops[item["todo"]] = shops
    return found


def wants_mall_name(found: Found) -> bool:
    """A mall nearby or a cluster of shops: ask once more for the mall that holds them."""
    return found.mall is not None or len(found.places) >= 4


def lists_for(found: Found, lists: list[dict[str, Any]], counts: dict[str, int]) -> list[str]:
    """The lists with something to buy that this place serves, in the configured order."""
    out = []
    for item in lists:
        todo = item["todo"]
        if counts.get(todo, 0) <= 0:
            continue
        if (
            (item["kind"] == KIND_MALL and found.mall)
            or found.shops.get(todo)
            or (
                item["kind"] == KIND_KEYWORDS
                and found.mall
                and _search(keywords_pattern(item.get("keywords")), found.mall.name)
            )
        ):
            out.append(todo)
    return out


def shown(items: list[str], most: int = MAX_ITEMS_SHOWN) -> str:
    text = ", ".join(items[:most])
    if len(items) > most:
        text += f" +{len(items) - most}"
    return text


def message(
    found: Found, todos: list[str], names: dict[str, str], items: dict[str, list[str]]
) -> str:
    """One line per list: its name, the shops for it when inside a mall, and what to buy."""
    lines = []
    for todo in todos:
        shops = list(dict.fromkeys(p.name for p in found.shops.get(todo, [])))
        where = f" ({shown(shops, MAX_SHOPS_SHOWN)})" if found.mall and shops else ""
        lines.append(f"{names.get(todo, todo)}{where}: {shown(items.get(todo, []))}")
    return "\n".join(lines)
