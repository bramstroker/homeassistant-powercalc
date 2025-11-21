from __future__ import annotations

from custom_components.powercalc.filter.outlier import OutlierFilter


def test_init_default_parameters():
    """Test initialization with default parameters."""
    filter = OutlierFilter()
    assert filter._window_size == 30
    assert filter._min_samples == 5
    assert filter._max_z_score == 3.5
    assert len(filter._values) == 0


def test_init_custom_parameters():
    """Test initialization with custom parameters."""
    filter = OutlierFilter(window_size=10, min_samples=3, max_z_score=2.0)
    assert filter._window_size == 10
    assert filter._min_samples == 3
    assert filter._max_z_score == 2.0
    assert len(filter._values) == 0


def test_values_property():
    """Test the values property."""
    filter = OutlierFilter()
    assert len(filter.values) == 0

    # Add some values
    filter._values.append(10.0)
    filter._values.append(20.0)

    # Check that values returns a tuple (immutable)
    values = filter.values
    assert isinstance(values, tuple)
    assert len(values) == 2
    assert 10.0 in values
    assert 20.0 in values


def test_accept_during_warmup():
    """Test that all values are accepted during warmup period."""
    filter = OutlierFilter(min_samples=3)

    # First min_samples values should be accepted unconditionally
    assert filter.accept(10.0) is True
    assert filter.accept(20.0) is True
    assert filter.accept(30.0) is True

    # Check that values were added to the window
    assert len(filter._values) == 3
    assert list(filter._values) == [10.0, 20.0, 30.0]


def test_accept_rejects_outliers():
    """Test that outliers are rejected after warmup period."""
    filter = OutlierFilter(min_samples=3, max_z_score=2.0)

    # Add initial values during warmup
    filter.accept(100.0)
    filter.accept(105.0)
    filter.accept(110.0)

    # This value is within normal range and should be accepted
    assert filter.accept(108.0) is True

    # This value is an outlier and should be rejected
    assert filter.accept(200.0) is False

    # Check that only the accepted value was added to the window
    assert len(filter._values) == 4
    assert 200.0 not in filter._values


def test_window_size_limit():
    """Test that the window size is limited to the specified value."""
    filter = OutlierFilter(window_size=3, min_samples=1)

    # Add more values than the window size
    filter.accept(10.0)
    filter.accept(20.0)
    filter.accept(30.0)
    filter.accept(40.0)

    # Check that only the most recent window_size values are kept
    assert len(filter._values) == 3
    assert list(filter._values) == [20.0, 30.0, 40.0]


def test_is_outlier_with_identical_values():
    """Test that when all values are identical, nothing is considered an outlier."""
    filter = OutlierFilter(min_samples=3)

    # Add identical values
    filter.accept(100.0)
    filter.accept(100.0)
    filter.accept(100.0)

    # Even a very different value should not be considered an outlier
    # because MAD is 0 in this case
    assert filter.accept(1000.0) is True


def test_is_outlier_with_extreme_values():
    """Test outlier detection with extreme values."""
    filter = OutlierFilter(min_samples=5, max_z_score=3.0)

    # Add some normal values
    filter.accept(100.0)
    filter.accept(105.0)
    filter.accept(95.0)
    filter.accept(110.0)
    filter.accept(90.0)

    # Test with values at different distances from the median
    assert filter.accept(120.0) is True  # Not an outlier
    assert filter.accept(150.0) is False  # Actually detected as an outlier
    assert filter.accept(200.0) is False  # Clear outlier, should be rejected


def test_is_outlier_with_negative_values():
    """Test outlier detection with negative values."""
    filter = OutlierFilter(min_samples=3, max_z_score=2.0)

    # Add some negative values
    filter.accept(-10.0)
    filter.accept(-15.0)
    filter.accept(-12.0)

    # Test with values at different distances from the median
    assert filter.accept(-20.0) is False  # Actually detected as an outlier
    assert filter.accept(10.0) is False  # Outlier (opposite sign), should be rejected


def test_empty_filter():
    """Test behavior with an empty filter."""
    filter = OutlierFilter()

    # Any value should be accepted when the filter is empty
    assert filter.accept(100.0) is True
    assert len(filter._values) == 1


def test_modified_z_score_calculation():
    """Test the modified Z-score calculation."""
    filter = OutlierFilter(min_samples=5, max_z_score=1.0)

    # Add values with a clear pattern
    filter.accept(10.0)
    filter.accept(11.0)
    filter.accept(9.0)
    filter.accept(10.5)
    filter.accept(9.5)

    # Median is 10.0, MAD is 0.5
    # For value=15.0, z = 0.6745 * (15.0 - 10.0) / 0.5 = 6.745
    # This is > max_z_score (1.0), so it should be rejected
    assert filter.accept(15.0) is False
