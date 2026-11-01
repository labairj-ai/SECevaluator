import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import db
from ai_summary import generate_summary
from email_builder import build_email, _comparison_table_html
from metrics import TeamStats, ConferenceStats, build_team_stats
from test_report_consistency import game


class OpponentCoverageTests(unittest.TestCase):
    def team(self, ratings):
        rows=[dict(team='SEC team',total=dict(wins=2,losses=0),conferenceGames=dict(wins=0,losses=0))]
        games=[dict(game(1),awayTeam='Rated'),dict(game(2),awayTeam='Unrated',awayConference='FCS')]
        games.append(dict(game(3),completed=False,homePoints=0,awayPoints=0))
        return build_team_stats(rows,games,ratings,{},'SEC')[0]

    def test_unrated_excluded_not_zero(self):
        team=self.team({'Rated':{'rating':-4}})
        self.assertEqual(team.sos_ooc,-4)
        self.assertEqual((team.sos_rated_games,team.sos_total_games),(1,2))
        self.assertEqual(team.sos_rating_total,-4)
        self.assertEqual(team.sos_str,'-4.00 (1/2)')

    def test_zero_is_a_real_rating(self):
        team=self.team({'Rated':{'rating':0}})
        self.assertEqual(team.sos_ooc,0)
        self.assertEqual((team.sos_rated_games,team.sos_total_games),(1,2))

    def test_all_unrated_shows_na_and_coverage(self):
        team=self.team({})
        self.assertIsNone(team.sos_ooc)
        self.assertEqual(team.sos_str,'N/A (0/2)')

    def test_conference_is_game_weighted_not_mean_of_team_means(self):
        teams=[TeamStats('A','SEC',sos_ooc=20,sos_rated_games=1,sos_total_games=2,sos_rating_total=20),
               TeamStats('B','SEC',sos_ooc=-10,sos_rated_games=3,sos_total_games=3,sos_rating_total=-30)]
        stats=ConferenceStats('SEC','SEC',teams)
        self.assertEqual(stats.avg_sos,-2.5)
        self.assertEqual(stats.sos_str,'-2.50 (4/5 games rated)')

    def test_no_conference_games_counted_as_ooc(self):
        rows=[dict(team='A',total=dict(wins=1,losses=0),conferenceGames=dict(wins=1,losses=0)),
              dict(team='B',total=dict(wins=0,losses=1),conferenceGames=dict(wins=0,losses=1))]
        games=[dict(game(1),homeTeam='A',awayTeam='B',awayConference='SEC')]
        teams=build_team_stats(rows,games,{'B':{'rating':20}}, {},'SEC')
        for team in teams:self.assertEqual((team.sos_rated_games,team.sos_total_games),(0,0))

    def test_partial_metric_has_explicit_coverage_and_no_winner_claim(self):
        sec=ConferenceStats('SEC','SEC',[TeamStats('A','SEC',sos_ooc=20,sos_rated_games=1,sos_total_games=2,sos_rating_total=20)])
        big=ConferenceStats('Big Ten','Big Ten',[TeamStats('B','Big Ten',sos_ooc=-10,sos_rated_games=1,sos_total_games=1,sos_rating_total=-10)])
        summary=generate_summary(sec,big,[],'',9)
        self.assertIn('rated opponents only; game-weighted',summary)
        self.assertIn('+20.00 (1/2 games rated)',summary)
        self.assertIn('-10.00 (1/1 games rated)',summary)
        self.assertIn('not a complete schedule-strength comparison',summary)
        self.assertNotIn('leads on average nonconference',summary)
        _,text,html=build_email(sec,big,[],summary,'',9,'SEC',2026)
        for body in (text,html):
            self.assertIn('1/2 games rated',body)
            self.assertIn('1/1 games rated',body)
        table=_comparison_table_html(sec,big)
        self.assertNotIn('background:#c8f0c8',table)
        self.assertNotIn('background:#f7c5c5',table)

    def test_empty_conference_has_no_invented_average(self):
        stats=ConferenceStats('SEC','SEC')
        self.assertIsNone(stats.avg_sos)
        self.assertEqual(stats.sos_str,'N/A (0/0 games rated)')


class CoverageHistoryTests(unittest.TestCase):
    def test_v2_rows_preserved_but_not_used_for_new_metric(self):
        with tempfile.TemporaryDirectory() as root, patch.object(db,'DB_PATH',str(Path(root)/'history.db')):
            with closing(sqlite3.connect(db.DB_PATH)) as c,c:
                c.execute('''CREATE TABLE report_snapshots (
                    year INTEGER,week INTEGER,season_type TEXT,conference TEXT,
                    avg_sp_rating REAL,avg_sos REAL,h2h_wins INTEGER,h2h_losses INTEGER,
                    total_wins INTEGER,total_losses INTEGER,ranked_teams INTEGER,
                    saved_at TEXT,metric_version INTEGER,poll_label TEXT,
                    PRIMARY KEY(year,season_type,week,conference))''')
                c.execute("INSERT INTO report_snapshots VALUES (2026,8,'regular','SEC',1,99,0,0,1,0,NULL,'original',2,NULL)")
            self.assertIsNone(db.load_prior_snapshot(2026,9,'SEC'))
            db.init_db()
            self.assertIsNone(db.load_prior_snapshot(2026,9,'SEC'))
            with closing(sqlite3.connect(db.DB_PATH)) as c:
                row=c.execute('SELECT avg_sos,saved_at,metric_version,sos_rated_games,sos_total_games FROM report_snapshots').fetchone()
            self.assertEqual(row,(99,'original',2,None,None))

    def test_v3_stores_and_recovers_coverage(self):
        with tempfile.TemporaryDirectory() as root, patch.object(db,'DB_PATH',str(Path(root)/'history.db')):
            db.init_db()
            sec=ConferenceStats('SEC','SEC',[TeamStats('S','SEC',sos_ooc=5,sos_rated_games=2,sos_total_games=3,sos_rating_total=10)])
            big=ConferenceStats('Big Ten','Big Ten')
            db.save_snapshots(2026,9,[('SEC',sec),('Big Ten',big)])
            prior=db.load_prior_snapshot(2026,10,'SEC')
            self.assertEqual((prior['avg_sos'],prior['sos_rated_games'],prior['sos_total_games']),(5,2,3))

if __name__=='__main__':unittest.main()
