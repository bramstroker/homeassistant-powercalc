from measure.visualization import PlotKind, PlotPoint, PlotSeries, PlotSpec, limit_plot_points
import pytest


@pytest.mark.parametrize("kind", list(PlotKind))
@pytest.mark.parametrize("limit", [1, 2, 3, 4, 8, 20, 40])
def test_point_limits_preserve_endpoints_and_input(kind: PlotKind, limit: int) -> None:
    points = [PlotPoint(x=index, y=100 if index == 10 else index % 3) for index in range(20)]
    plot = PlotSpec(
        id="test",
        title="Test",
        kind=kind,
        x_label="x",
        y_label="y",
        source="test",
        series=[PlotSeries(label=None, color=None, points=points)],
    )
    limited = limit_plot_points(plot, limit)
    result = limited.series[0].points
    assert len(result) <= limit
    assert result[0] == points[0]
    if limit > 1:
        assert result[-1] == points[-1]
    if kind is PlotKind.LINE and limit >= 4:
        assert max(point.y for point in result) == 100
    assert result == sorted(result, key=lambda point: point.x)
    assert plot.series[0].points == points
    result.clear()
    assert len(plot.series[0].points) == 20
    limited.series.clear()
    assert len(plot.series) == 1
