"""
delivery/models.py

DeliveryZone is the single source of truth for delivery pricing and
delivery-cost intelligence.

Architecture note (v1 pricing model):
    fee = base_fee + (per_km_rate * distance_km)

`distance_km` is manually estimated per zone for now (see
`average_distance_km`), but `calculate_fee()` accepts an optional
`distance_km` override. This is the intentional seam for future work:
when a live mapping/transportation API becomes available, only the
caller of `calculate_fee()` needs to change (pass a real distance) —
the model, schema, and every other consumer of the fee stay identical.
"""

from django.db import models


class DeliveryZone(models.Model):
    """
    A deliverable area with its own pricing and operational-cost profile.

    estimated_operational_cost is intentionally a single flat figure for v1
    (fuel + driver wages + vehicle maintenance + packaging + overhead, all
    rolled into one manually-estimated number by the business owner). It is
    deliberately not split into sub-fields yet — that decomposition, and/or
    replacing it with real cost data, is documented future work and should
    not require a schema change.
    """

    zone_name = models.CharField(
        max_length=150, unique=True,
        help_text="e.g. 'Freetown Central', 'Waterloo'"
    )

    base_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Flat starting fee for any delivery to this zone"
    )
    per_km_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Additional charge per kilometre"
    )
    average_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.00,
        help_text=(
            "Manually estimated typical delivery distance for this zone. "
            "Used by calculate_fee() when no live distance is supplied. "
            "This is the field a future mapping/distance API would replace "
            "or override on a per-order basis."
        )
    )

    estimated_operational_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text=(
            "Business owner's estimated operational cost of delivering to "
            "this zone (fuel, driver wages, vehicle maintenance, packaging, "
            "and other delivery overhead, combined into one figure for v1)."
        )
    )

    estimated_delivery_time_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Estimated time to complete a delivery to this zone"
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['zone_name']
        verbose_name = "Delivery Zone"
        verbose_name_plural = "Delivery Zones"

    def __str__(self):
        return self.zone_name

    def calculate_fee(self, distance_km=None):
        """
        Returns the delivery fee for this zone.

        distance_km: optional override. If not supplied, falls back to
        average_distance_km. Passing a real, live-computed distance here
        later (from a mapping API) requires no other changes anywhere
        in the system — this is the only method that needs to change.
        """
        if distance_km is None:
            distance_km = self.average_distance_km
        return self.base_fee + (self.per_km_rate * distance_km)

    def estimated_profit(self, distance_km=None):
        """Estimated profit for a delivery to this zone: fee - operational cost."""
        return self.calculate_fee(distance_km) - self.estimated_operational_cost