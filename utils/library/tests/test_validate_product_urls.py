from __future__ import annotations

import json
from pathlib import Path
from typing import Self
from urllib.error import HTTPError, URLError

import pytest

from utils.library import validate_product_urls as validator


class Response:
    def __init__(self, status: int = 200, url: str = "https://example.com/final") -> None:
        self.status = status
        self.url = url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url


def write_model(path: Path, product_url: object = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": "Example"}
    if product_url is not None:
        data["product_url"] = product_url
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_model_files_accepts_files_and_directories(tmp_path: Path) -> None:
    first = write_model(tmp_path / "manufacturer" / "one" / "model.json", "https://example.com/one")
    second = write_model(tmp_path / "manufacturer" / "two" / "model.json", "https://example.com/two")
    (tmp_path / "not-a-model.json").write_text("{}", encoding="utf-8")

    assert validator.model_files([tmp_path, first]) == [first, second]


def test_changed_model_files_ignores_deleted_and_non_model_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = write_model(tmp_path / "profile_library" / "brand" / "model" / "model.json")
    unrelated_model = write_model(tmp_path / "utils" / "model.json")
    changed = tmp_path / "changed.json"
    changed.write_text(
        json.dumps(
            [
                str(model.relative_to(tmp_path)),
                str(unrelated_model.relative_to(tmp_path)),
                "profile_library/gone/model.json",
                "README.md",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert validator.changed_model_files(changed) == [model.relative_to(tmp_path)]


def test_collect_product_urls_deduplicates_and_skips_non_strings(tmp_path: Path) -> None:
    first = write_model(tmp_path / "one" / "model.json", "https://example.com/product")
    second = write_model(tmp_path / "two" / "model.json", "https://example.com/product")
    third = write_model(tmp_path / "three" / "model.json", 123)

    assert validator.collect_product_urls([first, second, third]) == {
        "https://example.com/product": [first, second],
    }


def test_check_product_url_follows_redirects_and_accepts_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validator, "urlopen", lambda *_args, **_kwargs: Response())

    result = validator.check_product_url("https://example.com/product", 2)

    assert result.valid
    assert result.final_url == "https://example.com/final"


def test_check_product_url_rejects_non_https() -> None:
    result = validator.check_product_url("http://example.com/product", 2)

    assert not result.valid
    assert result.error == "URL must use HTTPS"


@pytest.mark.parametrize(
    "error,status,message",
    [
        (HTTPError("https://example.com", 404, "Not Found", {}, None), 404, "Not Found"),
        (URLError("DNS failure"), None, "DNS failure"),
        (TimeoutError("timed out"), None, "timed out"),
    ],
)
def test_check_product_url_reports_request_failures(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int | None,
    message: str,
) -> None:
    def raise_error(*_args: object, **_kwargs: object) -> Response:
        raise error

    monkeypatch.setattr(validator, "urlopen", raise_error)

    result = validator.check_product_url("https://example.com/product", 2)

    assert result.status == status
    assert result.error == message


def test_check_product_url_accepts_an_allowlisted_status(monkeypatch: pytest.MonkeyPatch) -> None:
    error = HTTPError("https://example.com", 403, "Forbidden", {}, None)

    def raise_error(*_args: object, **_kwargs: object) -> Response:
        raise error

    monkeypatch.setattr(validator, "urlopen", raise_error)
    allowlist_entry = validator.StatusAllowlistEntry(frozenset({403}), "Blocks automated clients")

    result = validator.check_product_url("https://example.com/product", 2, allowlist_entry)

    assert result.valid
    assert result.allowlist_reason == "Blocks automated clients"


def test_load_status_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "allowlist.json"
    path.write_text(
        json.dumps({"https://example.com/product": {"statuses": [403, 429], "reason": "Bot protection"}}),
        encoding="utf-8",
    )

    assert validator.load_status_allowlist(path) == {
        "https://example.com/product": validator.StatusAllowlistEntry(frozenset({403, 429}), "Bot protection")
    }


def test_failure_counts_are_loaded_updated_and_written(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    state = tmp_path / "state" / "failures.json"
    failed_url = "https://example.com/failed"
    recovered_url = "https://example.com/recovered"
    state.parent.mkdir()
    state.write_text(json.dumps({failed_url: 1, recovered_url: 2}), encoding="utf-8")
    results = [
        validator.ProductUrlResult(url=failed_url, status=404),
        validator.ProductUrlResult(url=recovered_url, status=200),
    ]

    assert validator.load_failure_counts(None) == {}
    assert validator.load_failure_counts(missing) == {}
    counts = validator.update_failure_counts(results, validator.load_failure_counts(state))
    assert counts == {failed_url: 2}

    output = tmp_path / "output" / "failures.json"
    validator.write_failure_counts(output, counts)
    assert json.loads(output.read_text(encoding="utf-8")) == {failed_url: 2}


def test_validate_product_urls_preserves_url_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        validator,
        "check_product_url",
        lambda url, _timeout, _allowlist_entry: validator.ProductUrlResult(url=url, status=200),
    )
    profiles = {"https://example.com/one": [], "https://example.com/two": []}

    results = validator.validate_product_urls(profiles, workers=2)

    assert [result.url for result in results] == list(profiles)


def test_build_report_lists_failures_and_profile_paths() -> None:
    url = "https://example.com/missing"
    profiles = {url: [Path("profile_library/brand/model/model.json")]}
    result = validator.ProductUrlResult(url=url, status=404, error="Not Found")

    report = validator.build_report([result], profiles)

    assert "failed for 1 of 1" in report
    assert "HTTP 404" in report
    assert "profile_library/brand/model/model.json" in report


def test_build_report_distinguishes_transient_and_threshold_failures() -> None:
    url = "https://example.com/missing"
    profiles = {url: []}
    result = validator.ProductUrlResult(url=url, status=404)

    transient_report = validator.build_report([result], profiles, {url: 2}, 3)
    failed_report = validator.build_report([result], profiles, {url: 3}, 3)

    assert "transient failure" in transient_report
    assert "2/3" in transient_report
    assert "after 3 consecutive" in failed_report
    assert "3/3" in failed_report


def test_build_report_accepts_empty_or_successful_results() -> None:
    assert validator.build_report([], {}) == "All 0 product URL(s) passed validation."


def test_build_report_mentions_allowlisted_results() -> None:
    result = validator.ProductUrlResult(
        url="https://example.com/product",
        status=403,
        allowlist_reason="Blocks automated clients",
    )

    assert validator.build_report([result], {}) == (
        "All 1 product URL(s) passed validation. (1 accepted through the non-200 allowlist.)"
    )


def test_main_appends_report_and_sets_failure_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = write_model(tmp_path / "brand" / "model" / "model.json", "https://example.com/missing")
    report = tmp_path / "report.md"
    status = tmp_path / "status.txt"
    report.write_text("Schema report", encoding="utf-8")
    status.write_text("success", encoding="utf-8")
    monkeypatch.setattr(
        validator,
        "validate_product_urls",
        lambda *_args, **_kwargs: [
            validator.ProductUrlResult(url="https://example.com/missing", status=404, error="Not Found"),
        ],
    )

    exit_code = validator.main([str(model), "--report", str(report), "--status", str(status)])

    assert exit_code == 1
    assert "## Product URLs" in report.read_text(encoding="utf-8")
    assert status.read_text(encoding="utf-8") == "failure"


def test_main_leaves_success_status_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = write_model(tmp_path / "brand" / "model" / "model.json", "https://example.com/product")
    status = tmp_path / "status.txt"
    status.write_text("success", encoding="utf-8")
    monkeypatch.setattr(
        validator,
        "validate_product_urls",
        lambda *_args, **_kwargs: [validator.ProductUrlResult(url="https://example.com/product", status=200)],
    )

    assert validator.main([str(model), "--status", str(status)]) == 0
    assert status.read_text(encoding="utf-8") == "success"


def test_main_only_fails_after_consecutive_failure_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://example.com/missing"
    model = write_model(tmp_path / "brand" / "model" / "model.json", url)
    state = tmp_path / "failures.json"
    monkeypatch.setattr(
        validator,
        "validate_product_urls",
        lambda *_args, **_kwargs: [validator.ProductUrlResult(url=url, status=503)],
    )

    for expected_count in (1, 2):
        assert (
            validator.main(
                [
                    str(model),
                    "--failure-state",
                    str(state),
                    "--failure-state-output",
                    str(state),
                    "--failure-threshold",
                    "3",
                ]
            )
            == 0
        )
        assert json.loads(state.read_text(encoding="utf-8")) == {url: expected_count}

    assert (
        validator.main(
            [
                str(model),
                "--failure-state",
                str(state),
                "--failure-state-output",
                str(state),
                "--failure-threshold",
                "3",
            ]
        )
        == 1
    )
    assert json.loads(state.read_text(encoding="utf-8")) == {url: 3}
