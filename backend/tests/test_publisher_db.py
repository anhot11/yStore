import pytest

from app.publisher_db import (
    get_approved_game_items,
    get_listing,
    get_publisher,
    list_listings,
    upsert_listing,
    upsert_publisher,
)
from app.scanner.base import ReviewStatus


def test_publisher_crud():
    upsert_publisher(
        publisher_id="dev_alpha",
        github_user="dev_alpha",
        repo_owner="dev_alpha",
        repo_name="cool-game-repo",
        installation_id="12345",
    )
    pub = get_publisher("dev_alpha")
    assert pub is not None
    assert pub["github_user"] == "dev_alpha"
    assert pub["repo_name"] == "cool-game-repo"


def test_listing_crud_and_status():
    upsert_listing(
        listing_id="dev_alpha.cool-game-repo",
        publisher_id="dev_alpha",
        repo="dev_alpha/cool-game-repo",
        tag="v1.0.0",
        version_code="1.0.0",
        title="Cool Game",
        short_description="Short desc",
        full_description="Full desc",
        icon_url="/cache/test.png",
        screenshots=["/cache/screen1.png"],
        changelog="First release",
        apk_download_url="https://example.com/cool.apk",
        sha256="112233445566",
        status=ReviewStatus.APPROVED,
        positives=0,
        total_engines=60,
    )

    listing = get_listing("dev_alpha.cool-game-repo")
    assert listing is not None
    assert listing["title"] == "Cool Game"
    assert listing["status"] == "approved"
    assert listing["positives"] == 0
    assert listing["screenshots"] == ["/cache/screen1.png"]

    # Test filtering
    approved_list = list_listings(status=ReviewStatus.APPROVED)
    assert any(l["id"] == "dev_alpha.cool-game-repo" for l in approved_list)

    rejected_list = list_listings(status=ReviewStatus.REJECTED)
    assert not any(l["id"] == "dev_alpha.cool-game-repo" for l in rejected_list)

    # Test game item conversion
    items = get_approved_game_items()
    assert any(item.id == "dev_alpha.cool-game-repo" for item in items)
    target = next(i for i in items if i.id == "dev_alpha.cool-game-repo")
    assert target.title == "Cool Game"
    assert target.download_url == "https://example.com/cool.apk"
