from __future__ import annotations

from custom_components.powercalc.filter.outlier import OutlierFilter


def test_accept_during_warmup() -> None:
    """Test that all values are accepted during warmup period."""
    outlier_filter = OutlierFilter(min_samples=3)

    # First min_samples values should be accepted unconditionally
    assert outlier_filter.accept(10.0) is True
    assert outlier_filter.accept(20.0) is True
    assert outlier_filter.accept(30.0) is True

    # Check that values were added to the window
    assert len(outlier_filter._values) == 3  # noqa: SLF001
    assert list(outlier_filter._values) == [10.0, 20.0, 30.0]  # noqa: SLF001


def test_accept_rejects_outliers() -> None:
    """Test that outliers are rejected after warmup period."""
    outlier_filter = OutlierFilter(min_samples=3, max_z_score=2.0, max_expected_step=50)

    # Add initial values during warmup
    outlier_filter.accept(100.0)
    outlier_filter.accept(105.0)
    outlier_filter.accept(110.0)

    # This value is within normal range and should be accepted
    assert outlier_filter.accept(108.0) is True

    # This value is an outlier and should be rejected
    assert outlier_filter.accept(200.0) is False

    # Check that only the accepted value was added to the window
    assert len(outlier_filter._values) == 4  # noqa: SLF001
    assert 200.0 not in outlier_filter._values  # noqa: SLF001


def test_window_size_limit() -> None:
    """Test that the window size is limited to the specified value."""
    outlier_filter = OutlierFilter(window_size=3, min_samples=1)

    outlier_filter.accept(10.0)
    outlier_filter.accept(20.0)
    outlier_filter.accept(30.0)
    outlier_filter.accept(40.0)

    assert len(outlier_filter._values) == 3  # noqa: SLF001
    assert list(outlier_filter._values) == [20.0, 30.0, 40.0]  # noqa: SLF001


def test_is_outlier_with_identical_values() -> None:
    """Test that when all values are identical, nothing is considered an outlier."""
    outlier_filter = OutlierFilter(min_samples=3)

    # Add identical values
    outlier_filter.accept(100.0)
    outlier_filter.accept(100.0)
    outlier_filter.accept(100.0)

    # Even a very different value should not be considered an outlier
    # because MAD is 0 in this case
    assert outlier_filter.accept(1000.0) is True


def test_is_outlier_with_extreme_values() -> None:
    """Test outlier detection with extreme values."""
    outlier_filter = OutlierFilter(min_samples=5, max_z_score=3.0)

    # Add some normal values
    outlier_filter.accept(100.0)
    outlier_filter.accept(105.0)
    outlier_filter.accept(95.0)
    outlier_filter.accept(110.0)
    outlier_filter.accept(90.0)

    # Test with values at different distances from the median
    assert outlier_filter.accept(120.0) is True  # Not an outlier
    assert outlier_filter.accept(3000) is False  # Actually detected as an outlier
    assert outlier_filter.accept(7000) is False  # Clear outlier, should be rejected


def test_drop_is_always_allowed() -> None:
    """Test outlier detection with negative values."""
    outlier_filter = OutlierFilter(min_samples=3, max_z_score=2.0)

    outlier_filter.accept(12.0)
    outlier_filter.accept(13.2)
    outlier_filter.accept(12.5)

    assert outlier_filter.accept(0.2) is True
