from scanner import find_records, merge, to_listing


def test_flexible_parser_and_new_change():
    payload = {
        "data": {
            "properties": [
                {
                    "propertyId": 123,
                    "address": "Dæmigata 1",
                    "postalCode": "101",
                    "price": "75.900.000 kr.",
                    "area": "92,4 m²",
                    "bedrooms": 2,
                    "bathrooms": 1,
                    "openHouseText": "Sunnudag 14:00–14:30",
                    "url": "/property/123",
                }
            ]
        }
    }
    records = find_records(payload)
    listing = to_listing(records[0], "2026-07-12T12:00:00+00:00")
    assert listing.listing_id == "123"
    assert listing.price_isk == "75900000"
    assert listing.size_m2 == "92.4"
    assert listing.postcode == "101"
    rows, changes = merge([listing], {}, 3)
    assert rows["123"]["status"] == "active"
    assert changes[0]["change_type"] == "new"


def test_price_change():
    listing = to_listing(
        {"id": "x", "address": "A", "price": 80_000_000}, "2026-07-12T12:00:00+00:00"
    )
    previous = {"x": {k: "" for k in listing.__dict__}}
    previous["x"].update(
        {
            "listing_id": "x",
            "price_isk": "79000000",
            "status": "active",
            "first_seen": "old",
        }
    )
    _, changes = merge([listing], previous, 3)
    assert changes[0]["change_type"] == "price"
    assert changes[0]["previous_price_isk"] == "79000000"
