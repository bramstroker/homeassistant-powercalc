import gzip
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy import profile_data
from custom_components.powercalc.strategy.profile_data import open_profile_csv


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
def test_uncompressed_size_limit(tmp_path: Path, compressed: bool, extra_bytes: int) -> None:
    """Accept the exact byte limit and reject even one extra decompressed byte."""
    limit = 64
    data = b"x" * (limit + extra_bytes)
    path = tmp_path / ("test.csv.gz" if compressed else "test.csv")
    path.write_bytes(gzip.compress(data) if compressed else data)

    with patch.object(profile_data, "MAX_UNCOMPRESSED_SIZE", limit):
        if extra_bytes > 0:
            with pytest.raises(StrategyConfigurationError, match="uncompressed size limit of 64 bytes"):
                open_profile_csv(str(path))
        else:
            with open_profile_csv(str(path)) as source:
                assert source.read() == data.decode()


def test_decompression_read_is_bounded(tmp_path: Path) -> None:
    """A highly compressible file without newlines must not be fully decompressed."""
    path = tmp_path / "bomb.csv.gz"
    path.write_bytes(gzip.compress(b"x" * (1024 * 1024)))
    with (
        patch.object(profile_data, "MAX_UNCOMPRESSED_SIZE", 1024),
        patch.object(gzip.GzipFile, "read", autospec=True, side_effect=gzip.GzipFile.read) as read,
        pytest.raises(StrategyConfigurationError, match="uncompressed size limit"),
    ):
        open_profile_csv(str(path))
    assert read.call_count == 1
    assert read.call_args.args[1] == 1025


def test_concatenated_gzip_members_share_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "test.csv.gz"
    path.write_bytes(gzip.compress(b"x" * 32) + gzip.compress(b"y" * 33))
    with (
        patch.object(profile_data, "MAX_UNCOMPRESSED_SIZE", 64),
        pytest.raises(StrategyConfigurationError, match="uncompressed size limit"),
    ):
        open_profile_csv(str(path))


@pytest.mark.parametrize("compressed", [False, True])
def test_utf8_csv_and_newlines(tmp_path: Path, compressed: bool) -> None:
    data = "🌈,1\r\n".encode()
    path = tmp_path / ("test.csv.gz" if compressed else "test.csv")
    path.write_bytes(gzip.compress(data) if compressed else data)
    with patch.object(profile_data, "MAX_UNCOMPRESSED_SIZE", len(data)), open_profile_csv(str(path)) as source:
        assert list(source) == ["🌈,1\n"]
    with (
        patch.object(profile_data, "MAX_UNCOMPRESSED_SIZE", len(data) - 1),
        pytest.raises(StrategyConfigurationError, match="uncompressed size limit"),
    ):
        open_profile_csv(str(path))
