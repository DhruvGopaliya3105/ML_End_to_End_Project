"""Emergency fallback: "we are out of it - who near you has it?"

Two sources, merged into one list:

1. SQL first (always works, no key, no internet)
   ``nearby_pharmacies`` + ``nearby_pharmacy_stocks`` are maintained by the
   super user for the shops the clinic actually has a tie-up with. If a
   partner shop has the tablet in stock it is shown on top with a price and a
   Call button.

2. Google Maps / Places (only when GOOGLE_MAPS_API_KEY is set in .env)
   Text Search finds chemists around the clinic/patient, Place Details adds
   the phone number and the opening hours. Anything Google returns is written
   back into ``nearby_pharmacies`` (upsert on google_place_id), so the next
   search is served from SQL and costs nothing.

If the key is missing, expired or the network is down, ``google_status`` says
exactly why and the page still shows the partner list - which is what matters
in an emergency.
"""

import json
import logging
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from sqlalchemy.orm import Session

from src.models.medicine import Medicine
from src.models.nearby_pharmacy import (
    NearbyPharmacy,
    NearbyPharmacyStock
)


logger = logging.getLogger(__name__)

LEGACY_TEXT_SEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"
LEGACY_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

TIMEOUT_SECONDS = float(os.getenv("PHARMACY_GOOGLE_TIMEOUT", "6"))
MAX_GOOGLE_RESULTS = int(os.getenv("PHARMACY_GOOGLE_MAX_RESULTS", "8"))


# =========================================================
# CONFIG
# =========================================================

def google_key() -> str | None:
    key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    return key or None


def google_enabled() -> bool:
    return google_key() is not None


def default_center() -> tuple[float, float]:
    try:
        lat = float(os.getenv("CLINIC_LATITUDE", "26.9124"))
        lng = float(os.getenv("CLINIC_LONGITUDE", "75.7873"))
    except (TypeError, ValueError):
        lat, lng = 26.9124, 75.7873
    return lat, lng


def default_city() -> str:
    return (os.getenv("CLINIC_CITY") or "Jaipur").strip() or "Jaipur"


def default_radius_m() -> int:
    try:
        return max(500, min(int(os.getenv("PHARMACY_NEARBY_RADIUS_M") or 5000), 50000))
    except (TypeError, ValueError):
        return 5000


# =========================================================
# GEO HELPER
# =========================================================

def distance_km(a_lat, a_lng, b_lat, b_lng) -> float | None:
    if None in (a_lat, a_lng, b_lat, b_lng):
        return None
    try:
        lat1, lon1, lat2, lon2 = map(float, (a_lat, a_lng, b_lat, b_lng))
    except (TypeError, ValueError):
        return None

    radius = 6371.0

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )

    return round(radius * 2 * math.asin(math.sqrt(h)), 2)


# =========================================================
# HTTP
# =========================================================

def _get_json(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})

    request = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "SanjeevaniClinic/1.0 (+pharmacy)",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


# =========================================================
# SQL PARTNER STOCK
# =========================================================

def partner_results(
    db: Session,
    medicine: Medicine | None,
    *,
    center: tuple[float, float] | None = None
) -> list[dict]:

    query = (
        db.query(NearbyPharmacy, NearbyPharmacyStock)
        .join(
            NearbyPharmacyStock,
            NearbyPharmacyStock.pharmacy_id == NearbyPharmacy.id
        )
        .filter(NearbyPharmacy.is_active.is_(True))
    )

    if medicine is not None:
        query = query.filter(NearbyPharmacyStock.medicine_id == medicine.id)

    rows = query.all()

    out: list[dict] = []

    for shop, stock in rows:

        qty = int(stock.stock or 0)

        out.append({
            "source": "PARTNER",
            "id": shop.id,
            "name": shop.name,
            "address": shop.address,
            "area": shop.area,
            "city": shop.city,
            "phone": shop.phone,
            "whatsapp": shop.whatsapp,
            "latitude": shop.latitude,
            "longitude": shop.longitude,
            "distance_km": distance_km(center[0], center[1], shop.latitude, shop.longitude)
            if center else shop.distance_km,
            "open_24x7": bool(shop.open_24x7),
            "opening_hours": shop.opening_hours,
            "rating": shop.rating,
            "maps_link": shop.maps_link,
            "tel_link": shop.tel_link,
            "is_partner": True,
            "stock": qty,
            "price": (
                float(stock.price) if stock.price is not None
                else (float(medicine.price) if medicine else None)
            ),
            "trust": stock.trust,
            "updated_at": (
                stock.updated_at.strftime("%d %b %Y %H:%M")
                if stock.updated_at else None
            ),
            "available": qty > 0,
        })

    out.sort(key=lambda row: (not row["available"], row["distance_km"] or 999))

    return out


def all_shops(db: Session, *, active_only: bool = True) -> list[NearbyPharmacy]:
    query = db.query(NearbyPharmacy)

    if active_only:
        query = query.filter(NearbyPharmacy.is_active.is_(True))

    return (
        query
        .order_by(
            NearbyPharmacy.is_partner.desc(),
            NearbyPharmacy.name.asc()
        )
        .all()
    )


def shop_to_dict(shop: NearbyPharmacy) -> dict:
    return {
        "id": shop.id,
        "name": shop.name,
        "address": shop.address,
        "area": shop.area,
        "city": shop.city,
        "pincode": shop.pincode,
        "phone": shop.phone,
        "whatsapp": shop.whatsapp,
        "latitude": shop.latitude,
        "longitude": shop.longitude,
        "distance_km": shop.distance_km,
        "open_24x7": bool(shop.open_24x7),
        "opening_hours": shop.opening_hours,
        "rating": shop.rating,
        "is_partner": bool(shop.is_partner),
        "is_active": bool(shop.is_active),
        "google_place_id": shop.google_place_id,
        "sync_status": shop.sync_status,
        "notes": shop.notes,
        "maps_link": shop.maps_link,
        "tel_link": shop.tel_link,
        "stock": [
            {
                "id": row.id,
                "medicine_id": row.medicine_id,
                "label": row.medicine_label or (
                    row.medicine.name if row.medicine else "unknown"
                ),
                "stock": row.stock,
                "price": float(row.price) if row.price is not None else None,
                "trust": row.trust,
            }
            for row in (shop.stocks or [])
        ],
    }


def upsert_shop(
    db: Session,
    data: dict,
    *,
    shop: NearbyPharmacy | None = None
) -> NearbyPharmacy:

    fields = (
        "name", "address", "area", "city", "pincode", "phone", "whatsapp",
        "latitude", "longitude", "distance_km", "open_24x7", "opening_hours",
        "rating", "is_partner", "google_place_id", "notes", "is_active",
    )

    if shop is None:
        place_id = data.get("google_place_id")
        if place_id:
            shop = (
                db.query(NearbyPharmacy)
                .filter(NearbyPharmacy.google_place_id == place_id)
                .first()
            )
        if shop is None and data.get("name"):
            shop = (
                db.query(NearbyPharmacy)
                .filter(NearbyPharmacy.name == data["name"])
                .first()
            )

    if shop is None:
        shop = NearbyPharmacy(name=(data.get("name") or "Unnamed shop")[:200])
        db.add(shop)

    for field in fields:
        if field in data and data[field] is not None:
            setattr(shop, field, data[field])

    if shop.latitude is not None and shop.longitude is not None:
        lat, lng = default_center()
        shop.distance_km = shop.distance_km or distance_km(lat, lng, shop.latitude, shop.longitude)

    db.flush()

    return shop


def set_shop_stock(
    db: Session,
    shop: NearbyPharmacy,
    medicine: Medicine,
    *,
    stock: int,
    price: float | None = None,
    trust: str = "VERIFIED"
) -> NearbyPharmacyStock:

    row = (
        db.query(NearbyPharmacyStock)
        .filter(
            NearbyPharmacyStock.pharmacy_id == shop.id,
            NearbyPharmacyStock.medicine_id == medicine.id,
        )
        .first()
    )

    if row is None:
        row = NearbyPharmacyStock(
            pharmacy_id=shop.id,
            medicine_id=medicine.id,
        )
        db.add(row)

    row.stock = max(0, int(stock or 0))
    row.price = float(price) if price not in (None, "") else float(medicine.price or 0)
    row.trust = (trust or "VERIFIED")[:20]
    row.medicine_label = medicine.name
    row.updated_at = datetime.utcnow()

    db.flush()

    return row


# =========================================================
# GOOGLE
# =========================================================

def _google_type() -> str:
    return (os.getenv("PHARMACY_GOOGLE_TYPE") or "pharmacy").strip() or "pharmacy"


def google_search(
    *,
    query: str,
    center: tuple[float, float],
    radius_m: int
) -> tuple[list[dict], str]:
    """Returns (results, status). Never raises."""

    key = google_key()

    if not key:
        return [], "no_key"

    params = {
        "query": query,
        "key": key,
        "radius": radius_m,
        "language": "en",
    }

    if center:
        params["location"] = f"{center[0]},{center[1]}"

    try:
        payload = _get_json(LEGACY_TEXT_SEARCH, params)
    except urllib.error.HTTPError as error:
        return [], f"http_{error.code}"
    except Exception as error:  # noqa: BLE001 - network / timeout / bad json
        logger.warning("Google Places text search failed: %s", error)
        return [], "network_error"

    status = payload.get("status")

    if status not in ("OK", "ZERO_RESULTS"):
        return [], f"api_{str(status).lower()}"

    results = []

    for place in (payload.get("results") or [])[:MAX_GOOGLE_RESULTS]:

        geometry = ((place.get("geometry") or {}).get("location") or {})

        results.append({
            "name": (place.get("name") or "")[:200],
            "address": (place.get("formatted_address") or "")[:500],
            "latitude": geometry.get("lat"),
            "longitude": geometry.get("lng"),
            "rating": place.get("rating"),
            "google_place_id": place.get("place_id"),
            "open_24x7": False,
            "opening_hours": None,
            "phone": None,
            "business_status": place.get("business_status"),
            "types": place.get("types") or [],
        })

    if os.getenv("PHARMACY_GOOGLE_DETAILS", "true").lower() != "false":
        _attach_details(results, key)

    return results, "ok"


def _attach_details(results: list[dict], key: str) -> None:

    for place in results[:5]:

        place_id = place.get("google_place_id")

        if not place_id:
            continue

        try:
            payload = _get_json(LEGACY_DETAILS, {
                "place_id": place_id,
                "key": key,
                "fields": ",".join([
                    "formatted_phone_number",
                    "international_phone_number",
                    "opening_hours/open_now",
                    "opening_hours/periods",
                    "utc_offset",
                ]),
            })
        except Exception:  # noqa: BLE001 - details are a nice-to-have
            continue

        detail = payload.get("result") or {}

        if not detail:
            continue

        place["phone"] = (
            detail.get("international_phone_number")
            or detail.get("formatted_phone_number")
        )

        hours = detail.get("opening_hours") or {}

        place["open_24x7"] = bool(hours.get("open_now")) and _is_all_day(hours)

        periods = hours.get("periods") or []

        if periods:
            try:
                first = periods[0]["time"]
                last = periods[0]["end"]["time"]
                place["opening_hours"] = f"{_hhmm(first)} - {_hhmm(last)}"
            except (KeyError, TypeError, IndexError):
                pass


def _hhmm(value: str) -> str:
    value = (value or "").replace(":", "")
    if len(value) >= 4:
        return f"{value[:2]}:{value[2:4]}"
    return value or ""


def _is_all_day(hours: dict) -> bool:
    periods = hours.get("periods") or []
    try:
        day = periods[0]["time"].replace(":", "")
        end = periods[0]["end"]["time"].replace(":", "")
        return day == "0000" and end in ("2359", "2400")
    except (KeyError, IndexError, TypeError):
        return False


def import_google_results(db: Session, results: list[dict]) -> int:
    """Write the Google hits into SQL so the next search is offline + free."""

    imported = 0

    for place in results:

        if not place.get("name"):
            continue

        upsert_shop(db, {
            "name": place["name"],
            "address": place.get("address"),
            "city": default_city(),
            "phone": place.get("phone"),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "rating": place.get("rating"),
            "open_24x7": bool(place.get("open_24x7")),
            "opening_hours": place.get("opening_hours"),
            "google_place_id": place.get("google_place_id"),
            "is_partner": False,
            "is_active": place.get("business_status") != "CLOSED_PERMANENTLY",
            "sync_status": "IN_SYNC",
        })

        imported += 1

    if imported:
        db.query(NearbyPharmacy).filter(
            NearbyPharmacy.last_synced_at.is_(None)
        ).update({"last_synced_at": datetime.utcnow()}, synchronize_session=False)
        db.commit()

    return imported


# =========================================================
# THE ONE CALL THE ROUTER MAKES
# =========================================================

def find_for_medicine(
    db: Session,
    medicine: Medicine | None,
    *,
    medicine_label: str | None = None,
    center: tuple[float, float] | None = None,
    radius_m: int | None = None,
    use_google: bool = True,
    persist_google: bool = True
) -> dict:

    center = center or default_center()
    radius_m = radius_m or default_radius_m()

    label = (
        medicine.name if medicine is not None
        else (medicine_label or "that medicine")
    )

    partner = partner_results(db, medicine, center=center)

    seen_place_ids = {
        shop.google_place_id
        for shop in db.query(NearbyPharmacy).filter(
            NearbyPharmacy.is_partner.is_(True)
        ).all()
        if shop.google_place_id
    }

    google_status = "skipped"
    google: list[dict] = []

    if use_google and google_enabled():
        query = f"pharmacy near {default_city()}"

        if medicine is not None and medicine.generic_name:
            query = f"chemist store {default_city()} {medicine.generic_name.split(' ')[0]}"

        google, google_status = google_search(
            query=query,
            center=center,
            radius_m=radius_m
        )

        google = [
            row for row in google
            if row.get("google_place_id") not in seen_place_ids
        ]

        if persist_google and google:
            try:
                import_google_results(db, google)
            except Exception:  # noqa: BLE001
                logger.exception("could not persist imported Google shops")

    elif use_google:
        google_status = "no_key"

    extra = []

    for place in google:
        lat, lng = place.get("latitude"), place.get("longitude")
        phone = place.get("phone")
        extra.append({
            "source": "GOOGLE",
            "id": None,
            "name": place.get("name"),
            "address": place.get("address"),
            "area": None,
            "city": default_city(),
            "phone": phone,
            "whatsapp": None,
            "latitude": lat,
            "longitude": lng,
            "distance_km": distance_km(center[0], center[1], lat, lng),
            "open_24x7": bool(place.get("open_24x7")),
            "opening_hours": place.get("opening_hours"),
            "rating": place.get("rating"),
            "maps_link": (
                "https://www.google.com/maps/dir/?api=1&destination="
                f"{lat},{lng}"
                if lat is not None and lng is not None
                else "https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote(f"{place.get('name')} {default_city()}")
            ),
            "tel_link": (
                "tel:" + "".join(c for c in phone if c.isdigit() or c == "+")
                if phone else None
            ),
            "is_partner": False,
            "stock": None,
            "price": None,
            "trust": "CALL_TO_CONFIRM",
            "updated_at": None,
            "available": None,
        })

    results = [row for row in partner if row["available"]] + extra + [
        row for row in partner if not row["available"]
    ]

    return {
        "medicine_id": medicine.id if medicine else None,
        "medicine_name": label,
        "generic_name": medicine.generic_name if medicine else None,
        "query": label,
        "center": {"latitude": center[0], "longitude": center[1]},
        "radius_m": radius_m,
        "results": results[:12],
        "partner_count": len(partner),
        "google_count": len(extra),
        "google_status": google_status,
        "google_enabled": google_enabled(),
        "note": (
            "Partner shops below are read from our own database, so their "
            "stock is what the shop reported to us."
            if google_status != "ok" else None
        ),
    }
