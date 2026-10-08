from measure.profile.models import ProfileMetadata
from pydantic import ValidationError
import pytest


def test_explicit_null_collections_remain_distinct_from_empty_collections() -> None:
    omitted = ProfileMetadata(manufacturer="Acme", model_id="MODEL-1")
    unspecified = ProfileMetadata(manufacturer="Acme", model_id="MODEL-1", aliases=None, gtins=None)
    cleared = ProfileMetadata(manufacturer="Acme", model_id="MODEL-1", aliases=[], gtins=[])

    assert omitted.aliases is None
    assert omitted.gtins is None
    assert unspecified.aliases is None
    assert unspecified.gtins is None
    assert "aliases" not in omitted.model_fields_set
    assert "aliases" in unspecified.model_fields_set
    assert cleared.aliases == ()
    assert cleared.gtins == ()


@pytest.mark.parametrize("model_id", [".", "..", "../MODEL", "MODEL/variant", "/absolute", "MODEL\\variant"])
def test_metadata_rejects_model_ids_that_could_escape_profile_directory(model_id: str) -> None:
    with pytest.raises(ValidationError, match="model_id contains unsafe characters"):
        ProfileMetadata(manufacturer="Acme", model_id=model_id)


@pytest.mark.parametrize("url", ["http://example.com/product", "ftp://example.com/product", "example.com/product"])
def test_metadata_rejects_product_urls_without_https(url: str) -> None:
    with pytest.raises(ValidationError, match="product_url must use https://"):
        ProfileMetadata(manufacturer="Acme", model_id="MODEL-1", product_url=url)
