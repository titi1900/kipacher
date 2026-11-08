#!/usr/bin/env python3
"""
KIPACHER – data/latest.json
Couverture France (maillage villes) + 30 EAN max.
Sources : Open Prices + Open Food Facts.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("ERREUR : pip install requests", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "latest.json"

OPEN_PRICES_BASE = "https://prices.openfoodfacts.org/api/v1"
OPEN_FOOD_FACTS_BASE = "https://world.openfoodfacts.org/api/v2"
USER_AGENT = "KIPACHER-updater/1.2 (GitHub Actions; open data; France mesh)"

# ---------------------------------------------------------------------------
# Maillage France (lat, lon, libellé)
# ---------------------------------------------------------------------------
CENTERS_PRESETS: dict[str, tuple[float, float, str]] = {
    # Grandes métropoles
    "paris": (48.8566, 2.3522, "Paris"),
    "lyon": (45.7640, 4.8357, "Lyon"),
    "marseille": (43.2965, 5.3698, "Marseille"),
    "toulouse": (43.6045, 1.4442, "Toulouse"),
    "nice": (43.7102, 7.2620, "Nice"),
    "nantes": (47.2184, -1.5536, "Nantes"),
    "montpellier": (43.6108, 3.8767, "Montpellier"),
    "strasbourg": (48.5734, 7.7521, "Strasbourg"),
    "bordeaux": (44.8378, -0.5792, "Bordeaux"),
    "lille": (50.6292, 3.0573, "Lille"),
    "rennes": (48.1173, -1.6778, "Rennes"),
    "reims": (49.2583, 4.0317, "Reims"),
    "saint-etienne": (45.4397, 4.3872, "Saint-Étienne"),
    "toulon": (43.1242, 5.9280, "Toulon"),
    "grenoble": (45.1885, 5.7245, "Grenoble"),
    "dijon": (47.3220, 5.0415, "Dijon"),
    "angers": (47.4784, -0.5632, "Angers"),
    "nimes": (43.8367, 4.3601, "Nîmes"),
    "le-havre": (49.4944, 0.1079, "Le Havre"),
    # Maillage complémentaire
    "dunkerque": (51.0343, 2.3768, "Dunkerque"),
    "calais": (50.9513, 1.8587, "Calais"),
    "amiens": (49.8941, 2.2958, "Amiens"),
    "rouen": (49.4432, 1.0993, "Rouen"),
    "caen": (49.1829, -0.3707, "Caen"),
    "brest": (48.3904, -4.4861, "Brest"),
    "le-mans": (48.0061, 0.1996, "Le Mans"),
    "tours": (47.3941, 0.6848, "Tours"),
    "orleans": (47.9029, 1.9093, "Orléans"),
    "nancy": (48.6921, 6.1844, "Nancy"),
    "metz": (49.1193, 6.1757, "Metz"),
    "mulhouse": (47.7508, 7.3359, "Mulhouse"),
    "besancon": (47.2378, 6.0241, "Besançon"),
    "clermont-ferrand": (45.7772, 3.0870, "Clermont-Ferrand"),
    "limoges": (45.8336, 1.2611, "Limoges"),
    "poitiers": (46.5802, 0.3404, "Poitiers"),
    "la-rochelle": (46.1603, -1.1511, "La Rochelle"),
    "pau": (43.2951, -0.3708, "Pau"),
    "bayonne": (43.4929, -1.4748, "Bayonne"),
    "perpignan": (42.6887, 2.8948, "Perpignan"),
    "avignon": (43.9493, 4.8055, "Avignon"),
    "valence": (44.9334, 4.8924, "Valence"),
    "annecy": (45.8992, 6.1294, "Annecy"),
    "ajaccio": (41.9267, 8.7369, "Ajaccio"),
}

# France entière = tous les centres du preset (ordre stable)
DEFAULT_CENTERS = list(CENTERS_PRESETS.keys())

# 30 EAN – priorité aux codes déjà vus avec prix en Open Prices
DEFAULT_EANS: list[str] = [
    "3017620422003",  # Nutella 400g
    "3017620425035",  # Nutella 1kg
    "3017620429484",  # Nutella 825g
    "8000500310427",  # Biscuits Nutella
    "5449000000996",  # Coca-Cola 33cl
    "5449000054227",  # Coca-Cola 1L
    "3274080005003",  # Cristaline 1.5L
    "3033490004743",  # Skyr Danone
    "3228857000906",  # Pain de mie Harrys
    "3046920029759",  # Chocolat / Lindt (souvent scanné)
    "3560070117619",  # MDD souvent présente OP
    "3250391809383",
    "3245412666816",
    "3564700009402",
    "3038350019800",
    "3155250358788",
    "8710438104320",
    "3266980011363",
    "3173286670012",
    "3095756211010",
    "3483974000183",
    "3608580001506",
    "3253560000316",
    "3017624010692",
    "3017620407901",
    "3254560156780",
    "3760151010455",
    "3341586100010",
    "8719201000150",
    "3017620422485",
]

REQUEST_TIMEOUT = 30
SLEEP = 0.25

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

EXCLUDED_TYPES = {
    "cinema", "stationery", "gift", "cosmetics", "charging_station",
    "clothes", "car", "fuel", "electronics", "mobile_phone", "books",
}


def http_get(url: str, params: dict | None = None) -> dict | list | None:
    try:
        r = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}] {url}?{urlencode(params or {})}")
            return None
        return r.json()
    except requests.RequestException as e:
        print(f"  [ERR] {e}")
        return None


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def fetch_nearby_stores(lat: float, lon: float, radius_km: float, size: int) -> list[dict]:
    data = http_get(
        f"{OPEN_PRICES_BASE}/locations/nearby",
        {"lat": lat, "lon": lon, "radius_km": radius_km, "size": size},
    )
    if not data or not isinstance(data, dict):
        return []
    items = data.get("items") or []
    print(f"  → {len(items)} magasin(s)")
    return items


def normalize_store(raw: dict) -> dict | None:
    lat, lon = raw.get("osm_lat"), raw.get("osm_lon")
    if lat is None or lon is None:
        return None
    stype = (raw.get("osm_tag_value") or raw.get("type") or "").lower()
    if stype in EXCLUDED_TYPES:
        return None
    store_id = str(raw.get("id") or f"osm-{raw.get('osm_id')}")
    name = raw.get("osm_name") or raw.get("osm_display_name") or f"Magasin {store_id}"
    return {
        "id": store_id,
        "name": name,
        "brand": raw.get("osm_brand") or None,
        "type": stype or "shop",
        "lat": float(lat),
        "lon": float(lon),
        "address": raw.get("osm_display_name") or None,
        "city": raw.get("osm_address_city") or None,
        "postcode": raw.get("osm_address_postcode") or None,
        "opening_hours": None,
        "open_prices_id": raw.get("id"),
        "price_count": raw.get("price_count") or 0,
        "product_count": raw.get("product_count") or 0,
        "prices": {},
    }


def fetch_latest_price(product_code: str, location_id: int | str) -> dict | None:
    data = http_get(
        f"{OPEN_PRICES_BASE}/prices",
        {
            "product_code": product_code,
            "location_id": location_id,
            "order_by": "-date",
            "size": 1,
        },
    )
    time.sleep(SLEEP)
    if not data or not isinstance(data, dict):
        return None
    items = data.get("items") or []
    if not items:
        return None
    p = items[0]
    try:
        price_f = float(p.get("price"))
    except (TypeError, ValueError):
        return None
    date_raw = p.get("date") or p.get("created")
    date_str = date_raw[:10] if isinstance(date_raw, str) and len(date_raw) >= 10 else None
    return {
        "price": round(price_f, 2),
        "available": True,
        "promo": bool(p.get("price_is_discounted")),
        "date": date_str,
    }


def fetch_product_off(ean: str) -> dict:
    data = http_get(f"{OPEN_FOOD_FACTS_BASE}/product/{ean}.json")
    time.sleep(SLEEP)
    if not data or data.get("status") != 1 or not data.get("product"):
        return {
            "ean": ean, "name": ean, "brand": None,
            "quantity": None, "category": None, "image": None,
        }
    p = data["product"]
    name = p.get("product_name") or p.get("product_name_fr") or p.get("generic_name") or ean
    return {
        "ean": ean,
        "name": name.strip() if isinstance(name, str) else str(ean),
        "brand": (p.get("brands") or "").split(",")[0].strip() or None,
        "quantity": p.get("quantity") or None,
        "category": None,
        "image": p.get("image_small_url") or p.get("image_url") or None,
    }


def collect_stores(center_keys: list[str], radius_km: float, max_per_center: int) -> dict[str, dict]:
    stores: dict[str, dict] = {}
    for key in center_keys:
        preset = CENTERS_PRESETS.get(key.lower())
        if not preset:
            print(f"  [WARN] centre inconnu : {key}")
            continue
        lat, lon, label = preset
        print(f"Centre : {label}")
        for raw in fetch_nearby_stores(lat, lon, radius_km, max_per_center):
            store = normalize_store(raw)
            if not store:
                continue
            prev = stores.get(store["id"])
            if prev is None or store["price_count"] > prev.get("price_count", 0):
                stores[store["id"]] = store
        time.sleep(SLEEP)
    return stores


def attach_prices(stores: dict[str, dict], eans: list[str], max_stores: int) -> None:
    ranked = sorted(
        stores.values(),
        key=lambda s: s.get("price_count") or 0,
        reverse=True,
    )[:max_stores]
    print(f"Prix : {len(ranked)} magasins × {len(eans)} EAN…")
    for store in ranked:
        loc_id = store.get("open_prices_id")
        if loc_id is None:
            continue
        for ean in eans:
            info = fetch_latest_price(ean, loc_id)
            if info:
                store["prices"][ean] = info


def build_products(eans: list[str], skip_off: bool) -> dict[str, dict]:
    if skip_off:
        return {
            ean: {
                "ean": ean, "name": ean, "brand": None,
                "quantity": None, "category": None, "image": None,
            }
            for ean in eans
        }
    print(f"Open Food Facts : {len(eans)} produits…")
    return {ean: fetch_product_off(ean) for ean in eans}


def fallback_dataset(now_iso: str) -> dict[str, Any]:
    return {
        "meta": {
            "generated_at": now_iso,
            "source": "fallback-demo",
            "version": "1.2",
            "currency": "EUR",
            "notes": "Fallback – APIs indisponibles",
        },
        "stores": [],
        "products": {},
    }


def build_dataset() -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    radius_km = env_float("RADIUS_KM", 10.0)
    max_per_center = env_int("MAX_STORES_PER_CENTER", 12)
    max_stores_to_price = env_int("MAX_STORES_TO_PRICE", 60)
    max_products = min(env_int("MAX_PRODUCTS", 30), 30)
    skip_off = os.environ.get("SKIP_OFF", "").strip().lower() in {"1", "true", "yes"}

    centers_raw = os.environ.get("CENTERS", "").strip()
    if centers_raw.lower() in {"all", "*", "france"}:
        center_keys = list(DEFAULT_CENTERS)
    elif centers_raw:
        center_keys = [c.strip() for c in centers_raw.split(",") if c.strip()]
    else:
        center_keys = list(DEFAULT_CENTERS)

    eans = DEFAULT_EANS[:max_products]

    print("=== KIPACHER update_prices v1.2 (France) ===")
    print(f"Centres : {len(center_keys)} → {center_keys[:5]}...")
    print(f"Rayon   : {radius_km} km | EAN : {len(eans)}")

    stores_map = collect_stores(center_keys, radius_km, max_per_center)
    if not stores_map:
        print("[WARN] aucun magasin – fallback")
        return fallback_dataset(now_iso)

    attach_prices(stores_map, eans, max_stores_to_price)
    products = build_products(eans, skip_off)

    stores_list = list(stores_map.values())
    for s in stores_list:
        s.pop("open_prices_id", None)

    priced = sum(1 for s in stores_list if s.get("prices"))
    print(f"Total : {len(stores_list)} magasins, {priced} avec prix, {len(products)} produits")

    return {
        "meta": {
            "generated_at": now_iso,
            "source": "open-prices+openfoodfacts",
            "version": "1.2",
            "currency": "EUR",
            "centers": center_keys,
            "centers_count": len(center_keys),
            "radius_km": radius_km,
            "ean_count": len(eans),
            "notes": "Maillage France – 30 EAN max – prix sur top magasins Open Prices",
        },
        "stores": stores_list,
        "products": products,
    }


def main() -> int:
    try:
        dataset = build_dataset()
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        dataset = fallback_dataset(datetime.now(timezone.utc).isoformat())

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK → {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())