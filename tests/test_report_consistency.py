import unittest
from unittest.mock import patch
import requests
import data_fetcher as d
from metrics import ConferenceStats, TeamStats, build_cross_game_results, build_conference_stats, h2h_leader
from ai_summary import generate_summary


def game(i, sec_wins=True):
    return dict(id=i, week=i, completed=True, homeTeam='SEC team', awayTeam='Big Ten team',
                homeConference='SEC', awayConference='Big Ten', homePoints=24 if sec_wins else 10,
                awayPoints=10 if sec_wins else 24, startDate='2026-09-01')


class ReportTests(unittest.TestCase):
    def test_api_failure_is_not_no_games(self):
        for error in (requests.Timeout(), requests.HTTPError(), ValueError()):
            with self.subTest(error=type(error)), patch.object(d, '_get', side_effect=error):
                with self.assertRaises(type(error)):
                    d.fetch_cross_conference_games(2026)

    def test_partial_season_failure_aborts(self):
        with patch.object(d, '_get', side_effect=[[game(1)], requests.Timeout()]):
            with self.assertRaises(requests.Timeout):
                d.fetch_cross_conference_games(2026)

    def test_deduplicate_and_filter(self):
        g = game(1)
        other = dict(game(2), homeConference='ACC')
        with patch.object(d, '_get', side_effect=[[g, other], [g]]):
            self.assertEqual(d.fetch_cross_conference_games(2026), [g])

    def test_malformed_response_aborts(self):
        for rows in ({'error': 'unavailable'}, [{}], [None]):
            with patch.object(d, '_get', return_value=rows):
                with self.assertRaises(ValueError):
                    d.fetch_cross_conference_games(2026)

    def test_three_results_and_summary_agree(self):
        games = build_cross_game_results([game(1), game(2), game(3, False)])
        sec = build_conference_stats('SEC', 'SEC', [TeamStats('S', 'SEC', sp_rating=5)], games, 'SEC')
        big = build_conference_stats('Big Ten', 'Big Ten', [TeamStats('B', 'Big Ten', sp_rating=9)], games, 'SEC')
        self.assertEqual(h2h_leader(sec, big), 'SEC leads 2-1')
        text = generate_summary(sec, big, games, 'No games played yet', 10, year=2025)
        self.assertIn('SEC leads 2-1', text)
        self.assertIn('Big Ten leads on average SP+', text)
        self.assertIn('2025', text)
        self.assertNotIn('No games played', text)

    def test_inconsistent_counts_rejected(self):
        with self.assertRaises(ValueError):
            generate_summary(ConferenceStats('SEC','SEC',h2h_wins=1), ConferenceStats('Big Ten','Big Ten'), [], '', 1)

    def test_empty_verified_season(self):
        text = generate_summary(ConferenceStats('SEC','SEC'), ConferenceStats('Big Ten','Big Ten'), [], '', 1)
        self.assertIn('No completed', text)
        self.assertIn('unavailable', text)

    def test_tied_scores_do_not_invent_a_winner(self):
        g = dict(game(1), homePoints=0, awayPoints=0)
        with self.assertRaises(ValueError):
            build_cross_game_results([g])

    def test_conference_disagreement_aborts(self):
        with patch.object(d, 'fetch_records', return_value=[]), patch.object(d, 'fetch_all_conference_games', side_effect=[[game(1)], []]):
            with self.assertRaisesRegex(ValueError, 'disagree'):
                d.fetch_all_data(2026, 10)

if __name__ == '__main__':
    unittest.main()
