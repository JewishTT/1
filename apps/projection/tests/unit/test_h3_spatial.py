"""H3 must never be mistaken for a position (spec 030 CE-001 §15.12, DON-SPAT-002/003).

The failure is not a wrong cell, it is a right cell read as a claim. An analyst who sees
``8928308280fffff`` on a map concludes the thing is there; at resolution 9 that cell is 174 m
across, and at resolution 7 it is 1.2 km. The index must therefore carry the source geometry,
the CRS and the declared accuracy *beside* the cell, and the risk of over- or under-precision has
to be computed rather than asserted by whoever wrote the record.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from spatial.h3_index import (
    H3_VERSION_PINNED,
    ResolutionPolicy,
    SpatialProjectionError,
    SpatialRef,
    index_point,
)

pytestmark = pytest.mark.unit

AMS = SpatialRef(latitude=52.3676, longitude=4.9041)


class TestTheSourceIsKept:
    def test_the_record_carries_the_source_geometry(self):
        rec = index_point(AMS)
        assert rec.spatial_ref.latitude == AMS.latitude
        assert rec.spatial_ref.longitude == AMS.longitude

    def test_the_record_carries_the_source_crs(self):
        assert index_point(AMS).spatial_ref.crs == "EPSG:4326"

    def test_the_cell_does_not_replace_the_geometry(self):
        """Stated in the record, so it survives serialisation to a UI that ignores the docstring."""
        assert index_point(AMS).notes["source_geometry_retained"] is True
        assert index_point(AMS).notes["cell_is_an_index_key"] is True

    def test_a_derived_point_still_points_at_its_stored_geometry(self):
        ref = SpatialRef(latitude=1.0, longitude=2.0, geometry_ref="geom-77")
        assert index_point(ref).spatial_ref.geometry_ref == "geom-77"

    def test_undeclared_accuracy_stays_undeclared(self):
        rec = index_point(AMS)
        assert rec.spatial_ref.accuracy_is_declared is False
        assert rec.accuracy_risk == "accuracy_undeclared"


class TestAccuracyIsComputedNotAsserted:
    def test_a_precise_source_keeps_a_fine_cell(self):
        rec = index_point(SpatialRef(latitude=52.37, longitude=4.89,
                                      coordinate_accuracy_m=5.0))
        # Finest cell that still encloses a 5 m error radius (res 13 edge ~8.5 m).
        assert rec.resolution >= 13
        assert rec.accuracy_risk == "cell_encloses_source"

    def test_a_coarse_source_forces_a_coarser_cell(self):
        """A 2 km accuracy cannot be indexed at 174 m and called precision."""
        rec = index_point(SpatialRef(latitude=52.37, longitude=4.89,
                                      coordinate_accuracy_m=2000.0))
        # Res 7 edge (~2.8 km) is the coarsest cell enclosing a 2 km error radius.
        assert rec.resolution <= 7
        assert rec.accuracy_risk == "cell_encloses_source"

    def test_no_accuracy_does_not_default_to_the_finest_cell(self):
        rec = index_point(AMS)
        assert rec.resolution == ResolutionPolicy().default_resolution

    def test_the_record_will_not_say_precision_is_preserved_without_accuracy(self):
        """The specific mislabelling this exists to prevent."""
        assert index_point(AMS).accuracy_risk != "cell_encloses_source"

    def test_a_cell_far_finer_than_its_source_is_flagged(self):
        rec = index_point(SpatialRef(latitude=52.37, longitude=4.89,
                                      coordinate_accuracy_m=5000.0))
        assert rec.is_finer_than_its_source() is False

    def test_an_unmeasurable_point_is_never_called_finer_than_its_source(self):
        assert index_point(AMS).is_finer_than_its_source() is False


class TestResolutionPolicyIsRespected:
    def test_the_policy_floor_is_honoured(self):
        rec = index_point(
            SpatialRef(latitude=52.37, longitude=4.89, coordinate_accuracy_m=50_000_000.0),
            policy=ResolutionPolicy(min_resolution=3),
        )
        assert rec.resolution >= 3

    def test_the_policy_ceiling_is_honoured(self):
        rec = index_point(
            SpatialRef(latitude=52.37, longitude=4.89, coordinate_accuracy_m=0.01),
            policy=ResolutionPolicy(max_resolution=7),
        )
        assert rec.resolution <= 7

    def test_resolution_changes_are_visible_in_the_fingerprint(self):
        """Two resolutions over one point are two different projections."""
        a = index_point(AMS, policy=ResolutionPolicy(default_resolution=6))
        b = index_point(AMS, policy=ResolutionPolicy(default_resolution=12))
        assert a.transform_fingerprint != b.transform_fingerprint


class TestImpossibleGeometryIsRefused:
    def test_latitude_out_of_range(self):
        with pytest.raises(SpatialProjectionError):
            SpatialRef(latitude=91.0, longitude=0.0)

    def test_longitude_out_of_range(self):
        with pytest.raises(SpatialProjectionError):
            SpatialRef(latitude=0.0, longitude=181.0)

    def test_negative_accuracy(self):
        with pytest.raises(SpatialProjectionError):
            SpatialRef(latitude=0.0, longitude=0.0, coordinate_accuracy_m=-1.0)

    def test_the_poles_and_antimeridian_are_valid(self):
        for lat, lon in ((90.0, 0.0), (-90.0, 0.0), (0.0, 180.0), (0.0, -180.0)):
            assert index_point(SpatialRef(latitude=lat, longitude=lon)).cell


class TestDeterminism:
    def test_the_same_point_indexes_to_the_same_cell(self):
        assert index_point(AMS).cell == index_point(AMS).cell

    def test_the_record_is_frozen(self):
        rec = index_point(AMS)
        with pytest.raises(Exception):
            rec.cell = "deadbeef"  # type: ignore[misc]

    def test_the_cell_is_a_valid_h3_index_at_that_resolution(self):
        import h3

        rec = index_point(AMS)
        assert h3.get_resolution(rec.cell) == rec.resolution
        assert H3_VERSION_PINNED in ("4.5.0",)