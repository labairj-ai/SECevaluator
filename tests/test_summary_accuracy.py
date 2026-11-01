import math
import unittest
from unittest.mock import patch
import data_fetcher as d
from metrics import (TeamStats, ConferenceStats, build_team_stats, build_cross_game_results,
                     build_conference_stats, compute_top_wins, compute_game_of_week)
from ai_summary import generate_summary
from email_builder import build_email
from test_report_consistency import game


class AccuracyTests(unittest.TestCase):
    def stats(self, games):
        cross = build_cross_game_results(games)
        sec = build_conference_stats('SEC', 'SEC', [TeamStats('S','SEC')], cross, 'SEC')
        big = build_conference_stats('Big Ten', 'Big Ten', [TeamStats('B','Big Ten')], cross, 'SEC')
        return sec, big, cross

    def test_swapped_win_counts_rejected_even_when_total_matches(self):
        sec, big, cross = self.stats([game(1), game(2), game(3,False)])
        sec.h2h_wins, sec.h2h_losses = 1, 2
        big.h2h_wins, big.h2h_losses = 2, 1
        with self.assertRaises(ValueError):
            generate_summary(sec,big,cross,'',10)

    def test_live_scores_are_not_final(self):
        row = dict(game(1), completed=False)
        sec,big,cross = self.stats([row])
        self.assertFalse(cross[0].played)
        self.assertEqual(sec.h2h_wins + sec.h2h_losses,0)
        self.assertEqual(compute_top_wins([row], {'SEC team'}, {'Big Ten team':{'rating':1}}, 'SEC'),[])
        self.assertIsNone(compute_game_of_week(cross,{}))

    def test_completed_without_scores_rejected(self):
        with self.assertRaises(ValueError):
            build_cross_game_results([dict(game(1), homePoints=None)])

    def test_wrong_conferences_rejected(self):
        with self.assertRaises(ValueError):
            build_cross_game_results([dict(game(1), awayConference='ACC')])

    def test_partial_ratings_are_not_conference_average(self):
        stats=ConferenceStats('SEC','SEC',[TeamStats('A','SEC',sp_rating=10),TeamStats('B','SEC')])
        self.assertIsNone(stats.avg_sp_rating)

    def test_missing_rankings_not_zero(self):
        sec,big,cross=self.stats([])
        text=generate_summary(sec,big,cross,'',10)
        self.assertIn('Rankings are unavailable',text)
        self.assertNotIn('Ranked teams (',text)

    def test_poll_name_and_week_reach_both_email_formats(self):
        sec,big,cross=self.stats([game(1)])
        sec.poll_label=big.poll_label='AP Top 25, week 9'
        text=generate_summary(sec,big,cross,'',10)
        _,plain,html=build_email(sec,big,cross,text,'SEC leads 1-0',10,'SEC',2026)
        for body in (text,plain,html):
            self.assertIn('AP Top 25, week 9',body)
            self.assertNotIn('CFP Top-25',body)
        self.assertNotIn('Top 12 earn automatic',html)

    def test_poll_fallback_tracks_actual_poll_week(self):
        polls=[dict(season=2026,week=9,seasonType='regular',polls=[dict(poll='AP Top 25',ranks=[dict(school='S',rank=1)])])]
        with patch.object(d,'_get',side_effect=[[],polls]):
            ranks=d.fetch_rankings(2026,10)
        self.assertEqual((ranks.poll,ranks.week),('AP Top 25',9))
        self.assertEqual(ranks,{'S':1})

    def test_no_poll_is_unavailable(self):
        with patch.object(d,'_get',return_value=[]):
            self.assertIsNone(d.fetch_rankings(2026,10).poll)

    def test_poll_error_not_silently_zero(self):
        with patch.object(d,'_get',side_effect=ValueError('bad response')):
            with self.assertRaises(ValueError): d.fetch_rankings(2026,10)

    def test_invalid_record_rejected(self):
        for record in (dict(team='S'),dict(team='S',total={'wins':0,'losses':0},conferenceGames={'wins':1,'losses':0})):
            with self.assertRaises(ValueError): build_team_stats([record],[],{},{},'SEC')

    def test_record_game_disagreement_rejected(self):
        row=dict(team='SEC team',total={'wins':2,'losses':0},conferenceGames={'wins':0,'losses':0})
        with self.assertRaisesRegex(ValueError,'disagree'):
            build_team_stats([row],[game(1)],{},{},'SEC')

    def test_valid_record_and_missing_opponent_rating(self):
        row=dict(team='SEC team',total={'wins':1,'losses':0},conferenceGames={'wins':0,'losses':0})
        teams=build_team_stats([row],[game(1)],{'SEC team':{'rating':1}},{},'SEC')
        self.assertIsNone(teams[0].sos_ooc)
        self.assertEqual(teams[0].nonconf_wins,1)

    def test_nonfinite_rating_rejected(self):
        row=dict(team='S',total={'wins':0,'losses':0},conferenceGames={'wins':0,'losses':0})
        for rating in (math.nan,math.inf,'10'):
            with self.assertRaises(ValueError):
                build_team_stats([row],[],{'S':{'rating':rating}},{},'SEC')

    def test_tied_ratings_do_not_claim_leader(self):
        sec,big,cross=self.stats([])
        sec.teams[0].sp_rating=big.teams[0].sp_rating=0
        text=generate_summary(sec,big,cross,'',10)
        self.assertIn('Neither conference leads on average SP+',text)

    def test_zero_ratings_appear_in_both_formats(self):
        sec,big,cross=self.stats([])
        sec.teams[0].sp_rating=0
        big.teams[0].sp_rating=-1
        text=generate_summary(sec,big,cross,'',10)
        _,plain,html=build_email(sec,big,cross,text,'',10,'SEC',2026)
        for body in (plain,html):
            self.assertIn('+0.00',body)
            self.assertIn('-1.00',body)

    def test_missing_ratings_explicit_in_text(self):
        sec,big,cross=self.stats([])
        _,plain,html=build_email(sec,big,cross,generate_summary(sec,big,cross,'',10),'',10,'SEC',2026)
        self.assertIn('Avg SP+: comparison unavailable',plain)
        self.assertIn('Avg OOC SOS: comparison unavailable',plain)
        self.assertIn('N/A',html)

if __name__=='__main__': unittest.main()
