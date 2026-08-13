from core.state import StateStore


def make_store(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.items = {
        "isbn13:1111111111111": {
            "first_seen": "2026-01-01",
            "record": {
                "title": "Handbook of Neurological Physiotherapy and Pediatric Physiotherapy Practice",
                "source": "crossref",
                "isbn13": "1111111111111",
                "publisher": "Elsevier",
            },
            "matched_keywords": ["rehabilitation"],  # stale: predates neuro/pediatric keywords
            "watchlist_short_title": None,
            "is_new_edition": False,
        },
        "isbn13:2222222222222": {
            "first_seen": "2026-01-02",
            "record": {
                "title": "Oxford Handbook of Sport & Exercise Medicine",
                "source": "crossref",
                "isbn13": "2222222222222",
                "publisher": "Oxford University PressOxford",
            },
            "matched_keywords": ["sports physiotherapy"],
            "watchlist_short_title": None,
            "is_new_edition": False,
        },
    }
    return store


def test_retag_updates_matched_keywords_when_new_keywords_match(tmp_path):
    store = make_store(tmp_path)
    include = ["rehabilitation", "neurological physiotherapy", "pediatric physiotherapy"]
    updated = store.retag(include, [])
    tags = store.items["isbn13:1111111111111"]["matched_keywords"]
    assert "neurological physiotherapy" in tags
    assert "pediatric physiotherapy" in tags
    assert updated >= 1


def test_retag_cleans_concatenated_publisher_names(tmp_path):
    store = make_store(tmp_path)
    store.retag(["sports physiotherapy"], [])
    assert store.items["isbn13:2222222222222"]["record"]["publisher"] == "Oxford University Press, Oxford"


def test_retag_preserves_first_seen_and_isbn(tmp_path):
    store = make_store(tmp_path)
    store.retag(["rehabilitation"], [])
    entry = store.items["isbn13:1111111111111"]
    assert entry["first_seen"] == "2026-01-01"
    assert entry["record"]["isbn13"] == "1111111111111"


def test_retag_returns_zero_when_nothing_changes(tmp_path):
    store = make_store(tmp_path)
    store.retag(["rehabilitation"], [])  # first pass settles matched_keywords + publisher
    updated = store.retag(["rehabilitation"], [])  # second pass: nothing left to change
    assert updated == 0


def test_retag_does_not_remove_items_even_if_now_excluded(tmp_path):
    store = make_store(tmp_path)
    store.retag(["rehabilitation"], ["oxford"])
    assert "isbn13:2222222222222" in store.items
