from chess_trainer.config import AppSettings, get_setting, load_settings, puzzle_config_from, save_settings, set_setting


def test_defaults_when_empty(db_session):
    s = load_settings(db_session)
    assert s == AppSettings()
    assert s.categories == ["rapid", "daily", "classical"]
    assert s.analysis_depth == 18 and s.puzzle_depth == 20
    assert s.mistake_threshold_cp == 100 and s.blunder_threshold_cp == 200
    assert s.avoid_gap_cp == 150 and s.new_per_day == 10 and s.leech_lapses == 5
    assert s.unique_gap_cp == 150
    assert s.new_order == "random"
    assert s.analysis_seconds == 15
    assert s.puzzle_search_seconds == 20
    assert s.classify_moves is True
    assert s.refute_wrong_moves is True


def test_save_normalizes_username_and_roundtrips(db_session):
    s = AppSettings(chesscom_username="  TheRealZibs ", categories=["rapid"], analysis_depth=12)
    saved = save_settings(db_session, s)
    assert saved.chesscom_username == "therealzibs"
    again = load_settings(db_session)
    assert again.chesscom_username == "therealzibs"
    assert again.categories == ["rapid"]
    assert again.analysis_depth == 12
    assert again.puzzle_depth == 20  # default preservado


def test_new_order_roundtrips(db_session):
    save_settings(db_session, AppSettings(new_order="recent"))
    assert load_settings(db_session).new_order == "recent"


def test_puzzle_config_from_maps_depth_without_a_separate_reply_depth():
    cfg = puzzle_config_from(AppSettings(puzzle_depth=20))
    assert cfg.depth == 20
    # a resposta do adversário usa a mesma busca do lance do solver: não há profundidade à parte.
    assert not hasattr(cfg, "reply_depth")


def test_puzzle_config_from_maps_unique_gap():
    cfg = puzzle_config_from(AppSettings(unique_gap_cp=250))
    assert cfg.unique_gap_cp == 250


def test_puzzle_config_from_maps_time_cap():
    cfg = puzzle_config_from(AppSettings(puzzle_search_seconds=30))
    assert cfg.search_seconds == 30
    assert not hasattr(cfg, "reply_seconds")


def test_raw_setting_helpers(db_session):
    assert get_setting(db_session, "last_imported_archive") is None
    set_setting(db_session, "last_imported_archive", "https://x/2026/09")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/09"
    set_setting(db_session, "last_imported_archive", "https://x/2026/10")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/10"


def test_tactics_settings_defaults(db_session):
    s = load_settings(db_session)
    assert (s.tactics_rating, s.tactics_window, s.lichess_min_plays, s.lichess_min_popularity) == (1200, 150, 2000, 90)
