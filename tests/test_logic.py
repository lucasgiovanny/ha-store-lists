"""Sorting real-looking Places answers into lists."""

from custom_components.store_lists.logic import (
    Place,
    classify,
    lists_for,
    message,
    parse_places,
    shown,
    wants_mall_name,
)

LISTS = [
    {"todo": "todo.casa", "kind": "home", "keywords": ""},
    {"todo": "todo.shopping", "kind": "mall", "keywords": ""},
    {"todo": "todo.construcao", "kind": "diy", "keywords": ""},
]
COUNTS = {"todo.casa": 2, "todo.shopping": 1, "todo.construcao": 3}

COLOMBO = [
    Place("a", "Flying Tiger Copenhagen CC Colombo", "gift_shop"),
    Place("b", "Samsung Experience Store Colombo", "cell_phone_store"),
    Place("c", "ZARA HOME", "home_goods_store"),
    Place("d", "Forever K", "shopping_mall"),
    Place("e", "Worten", "home_goods_store"),
    Place("f", "Continente", "supermarket"),
]


def test_parse_places() -> None:
    content = {
        "places": [{"id": "x", "displayName": {"text": "IKEA"}, "primaryType": "furniture_store"}]
    }
    assert parse_places(content) == [Place("x", "IKEA", "furniture_store")]
    assert parse_places(None) == []


def test_mall_shops_go_to_their_lists_and_electronics_stay_out() -> None:
    found = classify(COLOMBO, LISTS)
    assert [p.name for p in found.shops["todo.casa"]] == [
        "Flying Tiger Copenhagen CC Colombo",
        "ZARA HOME",
    ]
    assert "todo.construcao" not in found.shops
    assert found.mall and found.mall.name == "Forever K"
    assert wants_mall_name(found)
    assert lists_for(found, LISTS, COUNTS) == ["todo.casa", "todo.shopping"]


def test_retail_park_serves_home_and_diy_without_a_mall() -> None:
    places = [
        Place("ikea", "IKEA Loures - Loja Móveis e Decoração", "furniture_store"),
        Place("lm", "Leroy Merlin Loures", "home_improvement_store"),
    ]
    found = classify(places, LISTS)
    assert found.mall is None
    assert found.where and found.where.id == "ikea"
    assert lists_for(found, LISTS, COUNTS) == ["todo.casa", "todo.construcao"]


def test_empty_lists_and_general_shops_are_skipped() -> None:
    found = classify([Place("ct", "Continente Bom Dia", "supermarket")], LISTS)
    assert found.shops == {}
    assert found.where is None
    found = classify([Place("i", "IKEA", "furniture_store")], LISTS)
    assert lists_for(found, LISTS, {**COUNTS, "todo.casa": 0}) == []


def test_keywords_add_shops_to_any_kind() -> None:
    lists = [{"todo": "todo.desporto", "kind": "keywords", "keywords": "Decathlon, Sport Zone"}]
    found = classify([Place("d", "Decathlon Alfragide", "sporting_goods_store")], lists)
    assert lists_for(found, lists, {"todo.desporto": 1}) == ["todo.desporto"]


def test_message_names_the_mall_shops_and_caps_items() -> None:
    found = classify(COLOMBO, LISTS)
    text = message(
        found,
        ["todo.casa", "todo.shopping"],
        {"todo.casa": "Casa", "todo.shopping": "Shopping"},
        {"todo.casa": [f"item {i}" for i in range(1, 8)], "todo.shopping": ["ténis"]},
    )
    assert text == (
        "Casa (Flying Tiger Copenhagen CC Colombo, ZARA HOME): item 1, item 2, item 3, item 4, item 5 +2\n"
        "Shopping: ténis"
    )
    assert shown(["a"]) == "a"
