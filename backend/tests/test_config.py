from chess_trainer.config import AppSettings, get_setting, load_settings, puzzle_config_from, save_settings, set_setting


def test_defaults_when_empty(db_session):
    s = load_settings(db_session)
    assert s == AppSettings()
    assert s.categories == ["rapid", "daily", "classical"]
    assert s.analysis_depth == 18 and s.puzzle_depth == 20
    assert s.mistake_threshold_cp == 100 and s.blunder_threshold_cp == 200
    assert s.avoid_gap_cp == 150 and s.new_per_day == 10 and s.leech_lapses == 5
    assert s.new_order == "random"
    assert s.analysis_seconds == 15
    assert s.puzzle_search_seconds == 20 and s.puzzle_reply_seconds == 10
    assert s.classify_moves is True


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


def test_puzzle_config_from_derives_reply_depth():
    cfg = puzzle_config_from(AppSettings(puzzle_depth=20))
    assert cfg.depth == 20 and cfg.reply_depth == 14

    cfg = puzzle_config_from(AppSettings(puzzle_depth=12))
    assert cfg.depth == 12 and cfg.reply_depth == 12


def test_puzzle_config_from_clamps_reply_depth_to_depth():
    # profundidade abaixo do mínimo prático (12): reply_depth não pode superar depth.
    cfg = puzzle_config_from(AppSettings(puzzle_depth=10))
    assert cfg.depth == 10 and cfg.reply_depth == 10


def test_puzzle_config_from_maps_time_caps():
    cfg = puzzle_config_from(AppSettings(puzzle_search_seconds=30, puzzle_reply_seconds=12))
    assert cfg.search_seconds == 30 and cfg.reply_seconds == 12


def test_raw_setting_helpers(db_session):
    assert get_setting(db_session, "last_imported_archive") is None
    set_setting(db_session, "last_imported_archive", "https://x/2026/09")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/09"
    set_setting(db_session, "last_imported_archive", "https://x/2026/10")
    assert get_setting(db_session, "last_imported_archive") == "https://x/2026/10"


def test_tactics_settings_defaults(db_session):
    s = load_settings(db_session)
    assert (s.tactics_rating, s.tactics_window, s.lichess_min_plays, s.lichess_min_popularity) == (1200, 150, 2000, 90)
