import pytest

from src.product.data_locality import DataClass, DataLocalityPolicy, UnsafeCloudPayload


def test_product_objects_have_explicit_ownership_and_locality() -> None:
    policy = DataLocalityPolicy()
    assert policy.classify("public_instrument").data_class is DataClass.PUBLIC
    assert policy.classify("watchlist").owner == "user"
    assert policy.classify("watchlist").cloud_allowed is True
    assert policy.classify("portfolio_file").local_only is True
    assert policy.classify("datahub_credential").data_class is DataClass.SECRET


def test_cloud_boundary_rejects_local_paths_file_contents_and_credentials() -> None:
    policy = DataLocalityPolicy()
    policy.assert_cloud_safe({"symbol": "600519.SH", "watchlist_refs": ["600519.SH"]})

    for payload in (
        {"local_path": "C:/private/portfolio.csv"},
        {"file_content": "private positions"},
        {"api_key": "secret"},
    ):
        with pytest.raises(UnsafeCloudPayload):
            policy.assert_cloud_safe(payload)
