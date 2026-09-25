import pytest
from pydantic import ValidationError
from app.models import GameItem


def test_game_item_valid():
    item = GameItem(
        id="org.game.test",
        title="Test Game",
        source="fdroid",
        icon_url="/cache/icon.png",
        screenshots=["/cache/screen1.png"],
        description="A great game",
        developer="Awesome Studio",
        download_url="https://f-droid.org/repo/test.apk",
        tags=["Games", "Action"],
    )

    data = item.model_dump()
    assert data["id"] == "org.game.test"
    assert data["title"] == "Test Game"
    assert data["source"] == "fdroid"
    assert data["icon_url"] == "/cache/icon.png"
    assert data["screenshots"] == ["/cache/screen1.png"]
    assert data["description"] == "A great game"
    assert data["developer"] == "Awesome Studio"
    assert data["download_url"] == "https://f-droid.org/repo/test.apk"
    assert data["tags"] == ["Games", "Action"]


def test_game_item_defaults():
    item = GameItem(
        id="12345",
        title="Minimal Itch Game",
        source="itchio",
    )
    assert item.id == "12345"
    assert item.title == "Minimal Itch Game"
    assert item.source == "itchio"
    assert item.icon_url is None
    assert item.screenshots == []
    assert item.description == ""
    assert item.developer == ""
    assert item.download_url is None
    assert item.tags == []


def test_game_item_invalid_source():
    with pytest.raises(ValidationError):
        GameItem(
            id="test",
            title="Test",
            source="steam",  # Invalid: only fdroid or itchio allowed
        )
