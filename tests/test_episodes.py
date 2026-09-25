"""Marking a show watched covers every episode TMDB lists for it."""

from routers.api import all_episode_keys


def test_every_episode_of_every_season():
    seasons = [{"season_number": 1, "episode_count": 3},
               {"season_number": 2, "episode_count": 2}]
    assert all_episode_keys(seasons) == {(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)}


def test_no_seasons_no_episodes():
    assert all_episode_keys([]) == set()


def test_matches_title_page_numbering():
    # The title page counts progress as episodes 1..episode_count per season.
    seasons = [{"season_number": 4, "episode_count": 10}]
    keys = all_episode_keys(seasons)
    assert len(keys) == 10
    assert min(keys) == (4, 1) and max(keys) == (4, 10)
