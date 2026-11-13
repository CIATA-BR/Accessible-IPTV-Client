from pathlib import Path

import saved_searches


def test_corrupt_saved_search_history_is_preserved_and_reset(tmp_path):
    history = tmp_path / "programme-search-state.json"
    original = b"{not valid json"
    history.write_bytes(original)

    assert saved_searches.read_seen(str(history)) == {}

    backups = list(tmp_path.glob("programme-search-state.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert history.read_bytes() == original


def test_valid_saved_search_history_still_loads(tmp_path):
    history = tmp_path / "programme-search-state.json"
    history.write_text('{"' + "a" * 64 + '": 2000000000}', encoding="utf-8")

    loaded = saved_searches.read_seen(str(history))

    assert list(loaded) == ["a" * 64]
    assert list(tmp_path.glob("programme-search-state.json.corrupt-*")) == []
