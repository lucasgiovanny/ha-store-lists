"""Constants for Store Lists."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "store_lists"

CONF_API_KEY: Final = "api_key"
CONF_PEOPLE: Final = "people"
CONF_LISTS: Final = "lists"
CONF_TODO: Final = "todo"
CONF_KIND: Final = "kind"
CONF_KEYWORDS: Final = "keywords"
CONF_RADIUS: Final = "radius"
CONF_DWELL: Final = "dwell_minutes"
CONF_START: Final = "start"
CONF_END: Final = "end"
CONF_ERRORS_TO: Final = "errors_to"

KIND_HOME: Final = "home"
KIND_DIY: Final = "diy"
KIND_MALL: Final = "mall"
KIND_KEYWORDS: Final = "keywords"
KINDS: Final = [KIND_HOME, KIND_DIY, KIND_MALL, KIND_KEYWORDS]

DEFAULT_RADIUS: Final = 100
DEFAULT_DWELL: Final = 3
DEFAULT_START: Final = "08:00:00"
DEFAULT_END: Final = "23:00:00"
MALL_RADIUS: Final = 400
# Indoors the phone's fix drifts; worse than this and the nearest shop is a guess.
MAX_ACCURACY: Final = 150
MAX_ITEMS_SHOWN: Final = 5

PLACES_URL: Final = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK: Final = "places.id,places.displayName,places.types,places.primaryType"

MALL_TYPES: Final = ["shopping_mall", "department_store"]
HOME_TYPES: Final = ["furniture_store", "home_goods_store"]
DIY_TYPES: Final = ["home_improvement_store", "hardware_store"]
SEARCH_TYPES: Final = [*MALL_TYPES, *HOME_TYPES, *DIY_TYPES, "gift_shop"]
# Shops that sell a bit of everything never count as a home or DIY shop on their type alone.
GENERAL_TYPES: Final = [
    *MALL_TYPES,
    "supermarket",
    "grocery_store",
    "hypermarket",
    "discount_store",
    "warehouse_store",
]

HOME_BRANDS: Final = (
    r"IKEA|Zara Home|Espa[çc]o Casa|JYSK|H&M Home|Maisons du Monde|Conforama|Kasa|^Casa\b"
    r"|Flying Tiger|\bTiger\b|\bArea\b|Laskasas|Moviflor"
)
DIY_BRANDS: Final = r"Leroy Merlin|\bAKI\b|Bricomarch[ée]|Brico D[ée]p[ôo]t|Maxmat|Bauhaus|Bricor"
# Electronics chains Google often tags as home goods.
NOT_HOME: Final = r"Worten|Samsung|FNAC|\bMEO\b|Vodafone|\bNOS\b|Apple|Xiaomi|Media ?Markt"

SIGNAL_UPDATE: Final = f"{DOMAIN}_update"
EVENT_MATCH: Final = f"{DOMAIN}_match"
SERVICE_CHECK: Final = "check"
STORAGE_VERSION: Final = 1
