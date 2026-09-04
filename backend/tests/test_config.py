from chess_trainer.config import AppSettings, get_setting, load_settings, save_settings, set_setting


def test_defaults_when_empty(db_session):
    s = load_settings(db_session)
    assert s == AppSettings()
    assert s.categories == ["rapid", "daily", "classical"]
    assert s.analysis_depth == 18 and s.puzzle_depth == 20
    assert s.mistake_threshold_cp == 100 and s.blunder_threshold_cp == 200
    assert s.avoid_gap_cp == 150 and s.new_per_day == 10 and s.leech_lapses == 5


def test_save_normalizes_username_and_roundtrips(db_session):
    s = AppSettings(chesscom_username="  TheRealZibs ", categories=["rapid"], analysis_depth=12)
    saved = save_settings(db_session, s)
    assert saved.chesscom_username == "therealzibs"
    again = load_settings(db_session)
    assert again.chesscom_username == "therealzibs"
    assert again.categories == ["rapid"]
    assert again.analysis_depth == 12
    assert again.puzzle_depth == 20  # default preservado


def test_raw_setting_helpers(db_session):
    assert get_setting(db_session, "last_imported_archive") is None
    set_setting(db_session, "last_imported_archive", "https://x/2026/09")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/09"
    set_setting(db_session, "last_imported_archive", "https://x/2026/10")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/10"
