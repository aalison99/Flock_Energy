"""Checks on meter positions."""

import statistics

from app.domain.models import GeoPoint
from app.services.geo import haversine_km
from app.services.quality.models import Issue, QualityContext, Severity

OUTLIER_KM = 50.0


class MissingGeo:
    id = "missing_geo"
    severity = Severity.WARNING
    description = "A meter has no latitude/longitude."

    def run(self, ctx: QualityContext) -> list[Issue]:
        return [
            Issue(self.id, self.severity, "meter", m.meter_id, "meter has no position", {})
            for m in ctx.meters
            if m.geo is None
        ]


class GeoOutlier:
    id = "geo_outlier"
    severity = Severity.WARNING
    description = f"A meter is more than {OUTLIER_KM:g} km from the fleet's median position."

    def run(self, ctx: QualityContext) -> list[Issue]:
        positioned = [(m.meter_id, m.geo) for m in ctx.meters if m.geo is not None]
        if not positioned:
            return []
        centre = GeoPoint(
            statistics.median(g.lat for _, g in positioned),
            statistics.median(g.lng for _, g in positioned),
        )
        issues: list[Issue] = []
        for meter_id, geo in positioned:
            distance = haversine_km(centre, geo)
            if distance > OUTLIER_KM:
                issues.append(
                    Issue(
                        self.id,
                        self.severity,
                        "meter",
                        meter_id,
                        f"meter is {distance:.1f} km from the fleet's median position",
                        {
                            "distance_km": round(distance, 3),
                            "median_lat": round(centre.lat, 6),
                            "median_lng": round(centre.lng, 6),
                        },
                    )
                )
        return issues
