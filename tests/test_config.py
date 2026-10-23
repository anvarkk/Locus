from __future__ import annotations

import pytest

from locus.config import (
    PACKAGE_CONFIG_DIR,
    get_business_type,
    get_city,
    load_business_types,
    load_cities,
)


def test_packaged_defaults_exist() -> None:
    assert (PACKAGE_CONFIG_DIR / "cities.json").exists()
    assert (PACKAGE_CONFIG_DIR / "business_types.json").exists()


def test_cities_are_loaded() -> None:
    cities, default = load_cities()
    assert default in cities
    assert cities["kazan"].name == "Казань"
    assert cities["kazan"].radius_km > 0


def test_business_type_weights_sum_to_one() -> None:
    types, default = load_business_types()
    assert default in types
    for business in types.values():
        assert abs(sum(business.weights.values()) - 1.0) < 1e-9
        assert (
            "coffee" not in business.competitor_categories or business.slug == "coffee"
        )


def test_unknown_city_raises() -> None:
    with pytest.raises(KeyError):
        get_city("atlantis")


def test_business_type_lookup() -> None:
    assert get_business_type("coffee").title == "Кофейня"
    assert "parcel_locker" in get_business_type("parcel_locker").competitor_categories
