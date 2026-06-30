"""FastAPI routes for editing normalization data."""

import math
from collections import defaultdict

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from serieux import Partial, deserialize, serialize

from ..config import config
from ..model.classes import DatePrecision, Institution, Venue
from ..norm import NormalizationEntry
from ..utils import normalize_institution, normalize_venue
from .helpers import render_template


def install_normalization(app: FastAPI) -> FastAPI:
    hascap = app.auth.get_email_capability

    @app.get("/norm/venues", dependencies=[Depends(hascap("admin"))])
    async def norm_venues_page(request: Request):
        return render_template("norm_venues.html", request)

    @app.get("/norm/institutions", dependencies=[Depends(hascap("admin"))])
    async def norm_institutions_page(request: Request):
        return render_template("norm_institutions.html", request)

    @app.get("/api/v1/norm/normalize", dependencies=[Depends(hascap("admin"))])
    async def norm_normalize(name: str, type: str = "venue"):
        fn = normalize_institution if type == "institution" else normalize_venue
        return {"normalized": fn(name)}

    @app.get("/api/v1/norm/venues/by-name", dependencies=[Depends(hascap("admin"))])
    async def get_venues_by_name(name: str):
        if config.normalizer is None:
            return []
        name_lower = name.lower()
        result = []
        for original, entry in config.normalizer.venue_norm.items():
            s = serialize(Partial[Venue], entry.data)
            if s.get("name", "").lower() == name_lower:
                result.append({
                    "original": original,
                    "name": s.get("name", ""),
                    "type": s.get("type", ""),
                    "short_name": s.get("short_name", ""),
                    "date": (
                        DatePrecision.format(s["date"], s["date_precision"])
                        if "date" in s and "date_precision" in s
                        else ""
                    ),
                })
        return result

    @app.get("/api/v1/norm/institutions/by-name", dependencies=[Depends(hascap("admin"))])
    async def get_institutions_by_name(name: str):
        if config.normalizer is None:
            return []
        name_lower = name.lower()
        result = []
        for original, entry in config.normalizer.institution_norm.items():
            for partial in entry.data:
                s = serialize(Partial[Institution], partial)
                if s.get("name", "").lower() == name_lower:
                    result.append({
                        "original": original,
                        "name": s.get("name", ""),
                        "category": s.get("category", ""),
                        "country": s.get("country", ""),
                    })
        return result

    @app.get("/api/v1/norm/venues", dependencies=[Depends(hascap("admin"))])
    async def get_venue_norms(q: str = "", page: int = 1, page_size: int = 100):
        if config.normalizer is None:
            return {"items": [], "total": 0, "page": 1, "pages": 1}
        items = []
        for original, entry in config.normalizer.venue_norm.items():
            s = serialize(Partial[Venue], entry.data)
            items.append(
                {
                    "original": original,
                    "name": s.get("name", ""),
                    "type": s.get("type", ""),
                    "short_name": s.get("short_name", ""),
                    "date": (
                        DatePrecision.format(s["date"], s["date_precision"])
                        if "date" in s and "date_precision" in s
                        else ""
                    ),
                }
            )
        if q:
            ql = q.lower()
            items = [
                i
                for i in items
                if ql in i["original"].lower()
                or ql in i["name"].lower()
                or ql in i["short_name"].lower()
            ]
        total = len(items)
        pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, pages))
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "total": total,
            "page": page,
            "pages": pages,
        }

    @app.post("/api/v1/norm/venues")
    async def save_venue_norms(entries: list[dict], user: str = Depends(hascap("admin"))):
        if config.normalizer is None:
            raise HTTPException(status_code=501, detail="No normalizer configured")

        new_entries = {}
        for entry in entries:
            original = entry.get("original", "").strip()
            if not original:
                continue

            data_dict = {}
            if name := entry.get("name", "").strip():
                data_dict["name"] = name
            if type_ := entry.get("type", "").strip():
                data_dict["type"] = type_
            if short_name := entry.get("short_name", "").strip():
                data_dict["short_name"] = short_name
            if date_str := entry.get("date", "").strip():
                date_info = DatePrecision.assimilate_date(date_str, infer_precision=False)
                if date_info:
                    data_dict["date"] = date_info["date"].isoformat()
                    parts = date_str.split("-")
                    data_dict["date_precision"] = (
                        DatePrecision.day.value
                        if len(parts) >= 3
                        else DatePrecision.month.value
                        if len(parts) == 2
                        else DatePrecision.year.value
                    )

            if not data_dict:
                continue

            new_entries[original] = NormalizationEntry(
                origin=user,
                data=deserialize(Partial[Venue], data_dict),
            )

        current = dict(config.normalizer.venue_norm)
        current.update(new_entries)
        config.normalizer.venue_norm.save(current)
        return {
            "success": True,
            "message": f"Saved {len(new_entries)} venue normalization(s)",
        }

    @app.delete("/api/v1/norm/venues")
    async def delete_venue_norms(
        originals: list[str] = Body(...), user: str = Depends(hascap("admin"))
    ):
        if config.normalizer is None:
            raise HTTPException(status_code=501, detail="No normalizer configured")
        current = dict(config.normalizer.venue_norm)
        removed = sum(1 for k in originals if current.pop(k, None) is not None)
        config.normalizer.venue_norm.save(current)
        return {"success": True, "message": f"Deleted {removed} venue normalization(s)"}

    @app.get("/api/v1/norm/institutions", dependencies=[Depends(hascap("admin"))])
    async def get_institution_norms(q: str = "", page: int = 1, page_size: int = 100):
        if config.normalizer is None:
            return {"items": [], "total": 0, "page": 1, "pages": 1}

        # Groups paginated by original key; each page may have multiple rows per key
        groups = list(config.normalizer.institution_norm.items())
        if q:
            ql = q.lower()
            filtered = []
            for original, entry in groups:
                if ql in original.lower():
                    filtered.append((original, entry))
                    continue
                for partial in entry.data:
                    s = serialize(Partial[Institution], partial)
                    if ql in s.get("name", "").lower():
                        filtered.append((original, entry))
                        break
            groups = filtered

        total = len(groups)
        pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, pages))
        start = (page - 1) * page_size

        items = []
        for original, entry in groups[start : start + page_size]:
            for partial in entry.data:
                s = serialize(Partial[Institution], partial)
                items.append({
                    "original": original,
                    "name": s.get("name", ""),
                    "category": s.get("category", ""),
                    "country": s.get("country", ""),
                })
        return {"items": items, "total": total, "page": page, "pages": pages}

    @app.post("/api/v1/norm/institutions")
    async def save_institution_norms(
        entries: list[dict], user: str = Depends(hascap("admin"))
    ):
        if config.normalizer is None:
            raise HTTPException(status_code=501, detail="No normalizer configured")

        # Group flat rows by original; each group becomes a list[Partial[Institution]]
        groups: dict = defaultdict(list)
        for entry in entries:
            original = entry.get("original", "").strip()
            if not original:
                continue
            data_dict = {}
            if name := entry.get("name", "").strip():
                data_dict["name"] = name
            if category := entry.get("category", "").strip():
                data_dict["category"] = category
            if country := entry.get("country", "").strip():
                data_dict["country"] = country
            if data_dict:
                groups[original].append(deserialize(Partial[Institution], data_dict))

        new_entries = {
            original: NormalizationEntry(origin=user, data=partials)
            for original, partials in groups.items()
        }
        current = dict(config.normalizer.institution_norm)
        current.update(new_entries)
        config.normalizer.institution_norm.save(current)
        return {
            "success": True,
            "message": f"Saved {len(new_entries)} institution normalization(s)",
        }

    @app.delete("/api/v1/norm/institutions")
    async def delete_institution_norms(
        originals: list[str] = Body(...), user: str = Depends(hascap("admin"))
    ):
        if config.normalizer is None:
            raise HTTPException(status_code=501, detail="No normalizer configured")
        current = dict(config.normalizer.institution_norm)
        removed = sum(1 for k in originals if current.pop(k, None) is not None)
        config.normalizer.institution_norm.save(current)
        return {
            "success": True,
            "message": f"Deleted {removed} institution normalization(s)",
        }

    return app
