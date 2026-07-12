from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
CSV_PATH = ROOT / "data" / "listings.csv"
CHANGES_PATH = ROOT / "data" / "latest_changes.json"
DEBUG_PATH = ROOT / "debug" / "last_response.json"
SOURCE = "fasteignir.visir.is"
BASE_URL = "https://fasteignir.visir.is"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("listing-monitor")


@dataclass
class Listing:
    listing_id: str = ""
    address: str = ""
    postcode: str = ""
    locality: str = ""
    price_isk: str = ""
    size_m2: str = ""
    rooms: str = ""
    bedrooms: str = ""
    bathrooms: str = ""
    property_type: str = ""
    open_house: str = ""
    listed_date: str = ""
    source: str = SOURCE
    url: str = ""
    first_seen: str = ""
    last_seen: str = ""
    status: str = "active"
    change_type: str = ""
    previous_price_isk: str = ""
    raw_json: str = ""


FIELDNAMES = [f.name for f in fields(Listing)]
CSV_COLUMNS = [
    "listing_id",
    "url",
    "address",
    "postcode",
    "price_isk",
    "size_m2",
    "rooms",
    "bedrooms",
    "bathrooms",
    "property_type",
    "open_house",
    "listed_date",
    "status",
    "change_type",
    "previous_price_isk",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out[path] = value
            out.update(flatten(value, path))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.update(flatten(value, f"{prefix}[{index}]"))
    return out


def pick(item: dict[str, Any], aliases: Iterable[str]) -> Any:
    flat = flatten(item)
    alias_keys = {normalize_key(a) for a in aliases}
    for path, value in flat.items():
        leaf = re.split(r"\.|\[", path)[-1].rstrip("]")
        if normalize_key(leaf) in alias_keys and value not in (None, "", [], {}):
            return value
    return ""


def number(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return str(int(value) if float(value).is_integer() else value)
    text = str(value).strip().replace("\xa0", " ")
    text = re.sub(r"(?<=\d)[.\s](?=\d{3}(?:\D|$))", "", text)
    text = text.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return match.group(0) if match else ""


def text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        return "; ".join(text(v) for v in value if text(v))
    if isinstance(value, dict):
        return "; ".join(f"{k}: {text(v)}" for k, v in value.items() if text(v))
    return re.sub(r"\s+", " ", str(value)).strip()


def format_open_house(value: Any) -> str:
    if isinstance(value, dict):
        parts = {k: str(v).strip() for k, v in value.items() if v}
    elif isinstance(value, str) and value.strip():
        parts = {}
        for segment in value.split(";"):
            if ":" in segment:
                k, v = segment.split(":", 1)
                parts[k.strip()] = v.strip()
    else:
        return ""
    date_str = parts.get("date", "")
    start = parts.get("time_start", "")[:5]
    end = parts.get("time_end", "")[:5]
    if not date_str:
        return ""
    if start and end:
        return f"{date_str}, {start}–{end}"
    return date_str


def find_records(payload: Any) -> list[dict[str, Any]]:
    candidates: list[list[dict[str, Any]]] = []

    def walk(value: Any) -> None:
        if (
            isinstance(value, list)
            and value
            and all(isinstance(x, dict) for x in value)
        ):
            candidates.append(value)
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    if not candidates:
        return []

    def score(records: list[dict[str, Any]]) -> tuple[int, int]:
        sample = records[:5]
        vocabulary = {
            "price",
            "verd",
            "address",
            "street",
            "gata",
            "postalcode",
            "postcode",
            "zip",
            "area",
            "size",
            "rooms",
            "bedrooms",
            "property",
            "url",
            "id",
        }
        hits = 0
        for record in sample:
            keys = {normalize_key(k.split(".")[-1]) for k in flatten(record)}
            hits += len(keys & vocabulary)
        return hits, len(records)

    return max(candidates, key=score)


def to_listing(item: dict[str, Any], seen_at: str) -> Listing:
    url_value = text(
        pick(item, ["url", "link", "href", "propertyUrl", "detailsUrl", "slug"])
    )
    if url_value and not url_value.startswith("http"):
        url_value = urljoin(BASE_URL, url_value)

    listing_id = text(
        pick(
            item,
            [
                "id",
                "propertyId",
                "property_id",
                "objectId",
                "object_id",
                "fastanumer",
                "eignId",
            ],
        )
    )
    street_number = text(
        pick(item, ["street_number", "streetNumber", "house_number", "husnumer"])
    )
    address = text(
        pick(
            item,
            [
                "address",
                "street",
                "streetName",
                "gata",
                "heimilisfang",
                "title",
                "name",
            ],
        )
    )
    if street_number and address and street_number not in address:
        address = f"{address} {street_number}"
    postcode = number(
        pick(item, ["postcode", "postalCode", "zip", "postnumer", "postnr"])
    )
    locality = text(
        pick(
            item, ["locality", "city", "town", "municipality", "stadur", "sveitarfelag"]
        )
    )

    if not listing_id:
        fingerprint = url_value or "|".join(
            [
                address,
                postcode,
                number(pick(item, ["price", "verd"])),
                number(pick(item, ["size", "area"])),
            ]
        )
        listing_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:20]

    return Listing(
        listing_id=listing_id,
        address=address,
        postcode=postcode,
        locality=locality,
        price_isk=number(
            pick(item, ["price", "askingPrice", "salePrice", "verd", "verð"])
        ),
        size_m2=number(
            pick(
                item,
                [
                    "size",
                    "area",
                    "squareMeters",
                    "sqm",
                    "fermetrar",
                    "flatarmal",
                    "flatarmál",
                ],
            )
        ),
        rooms=number(pick(item, ["rooms", "roomCount", "herbergi"])),
        bedrooms=number(pick(item, ["bedrooms", "bedroomCount", "svefnherbergi"])),
        bathrooms=number(
            pick(item, ["bathrooms", "bathroomCount", "badherbergi", "baðherbergi"])
        ),
        property_type=text(
            pick(item, ["propertyType", "type", "category", "tegund", "flokkur"])
        ),
        open_house=text(
            pick(
                item,
                [
                    "openHouse",
                    "open_house",
                    "openHouseTime",
                    "openHouseText",
                    "opidHus",
                    "opiðHús",
                ],
            )
        ),
        listed_date=text(
            pick(
                item,
                [
                    "listedDate",
                    "published",
                    "publishedAt",
                    "created",
                    "date",
                    "skraningardagur",
                ],
            )
        ),
        source=SOURCE,
        url=url_value or f"{BASE_URL}/property/{listing_id}",
        first_seen=seen_at,
        last_seen=seen_at,
        status="active",
        raw_json=json.dumps(item, ensure_ascii=False, separators=(",", ":")),
    )


def fetch_payload(config: dict[str, Any]) -> Any:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; personal-listing-monitor/1.0; +https://github.com/)",
        "Accept": "application/json,text/plain,*/*",
        "Referer": config["search_url"],
    }
    response = requests.get(
        config["api_url"], params=config["query"], headers=headers, timeout=45
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise RuntimeError(
            f"Search endpoint returned non-JSON content ({response.headers.get('content-type')}): {response.text[:300]}"
        ) from exc
    DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEBUG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def load_rows() -> dict[str, dict[str, str]]:
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return {
            row["listing_id"]: row
            for row in csv.DictReader(handle)
            if row.get("listing_id")
        }


def save_rows(rows: dict[str, dict[str, str]]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        rows.values(),
        key=lambda r: (
            r.get("status") != "active",
            r.get("postcode", ""),
            r.get("address", ""),
        ),
    )
    for row in ordered:
        row["open_house"] = format_open_house(row.get("open_house", ""))
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ordered)


def merge(
    current: list[Listing], previous: dict[str, dict[str, str]], missing_runs: int
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    changes: list[dict[str, str]] = []
    seen_ids = set()
    rows = dict(previous)

    for listing in current:
        seen_ids.add(listing.listing_id)
        old = previous.get(listing.listing_id)
        row = asdict(listing)
        if not old:
            row["change_type"] = "new"
            changes.append(row.copy())
        else:
            row["first_seen"] = old.get("first_seen") or listing.first_seen
            change_parts = []
            if listing.price_isk and listing.price_isk != old.get("price_isk", ""):
                row["previous_price_isk"] = old.get("price_isk", "")
                change_parts.append("price")
            if listing.open_house != old.get("open_house", ""):
                change_parts.append("open_house")
            if old.get("status") != "active":
                change_parts.append("reactivated")
            row["change_type"] = "+".join(change_parts)
            if change_parts:
                changes.append(row.copy())
        rows[listing.listing_id] = row

    # A missing counter is kept inside raw_json metadata to avoid another public CSV column.
    for listing_id, old in list(rows.items()):
        if listing_id in seen_ids or old.get("status") != "active":
            continue
        try:
            raw = json.loads(old.get("raw_json") or "{}")
        except json.JSONDecodeError:
            raw = {}
        count = int(raw.get("_monitor_missing_runs", 0)) + 1
        raw["_monitor_missing_runs"] = count
        old["raw_json"] = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
        old["change_type"] = ""
        if count >= missing_runs:
            old["status"] = "inactive"
            old["change_type"] = "inactive"
            changes.append(old.copy())

    return rows, changes


def notify_telegram(changes: list[dict[str, str]]) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id or not changes:
        return
    lines = [f"🏠 Fasteignavakt: {len(changes)} breyting(ar)"]
    for item in changes[:15]:
        price = (
            f"{int(float(item['price_isk'])):,} kr.".replace(",", ".")
            if item.get("price_isk")
            else "verð vantar"
        )
        lines.append(
            f"• {item.get('change_type')}: {item.get('address')} {item.get('postcode')} — {price}\n{item.get('url')}"
        )
    if len(changes) > 15:
        lines.append(f"…og {len(changes) - 15} til viðbótar")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()


def main() -> int:
    config = load_config()
    seen_at = now_iso()
    payload = fetch_payload(config)
    records = find_records(payload)
    if not records:
        raise RuntimeError(
            f"No listing records found in API response. Inspect {DEBUG_PATH}"
        )
    listings = [to_listing(record, seen_at) for record in records]
    listings = [x for x in listings if x.address or x.url]
    listings = [
        x
        for x in listings
        if x.price_isk and 65_000_000 <= float(x.price_isk) <= 80_000_000
    ]
    listings = [x for x in listings if x.property_type == "Fjölbýlishús"]
    listings = [x for x in listings if x.size_m2 and 70 <= float(x.size_m2) <= 120]
    if not listings:
        raise RuntimeError(
            f"Records were found, but none could be parsed. Inspect {DEBUG_PATH}"
        )

    previous = load_rows()
    rows, changes = merge(
        listings, previous, int(config.get("missing_runs_before_inactive", 3))
    )
    save_rows(rows)
    CHANGES_PATH.write_text(
        json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    notify_telegram(changes)
    log.info(
        "Parsed %s listings; %s changes; database now has %s rows",
        len(listings),
        len(changes),
        len(rows),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log.exception("Scan failed: %s", exc)
        raise SystemExit(1)
