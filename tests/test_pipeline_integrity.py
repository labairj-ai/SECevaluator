import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, Mock

import requests
import data_fetcher as d
import db
import secevaluator as app
from ai_summary import generate_summary
from email_builder import build_email, _comparison_table_html, send_gmail
from metrics import (TeamStats, ConferenceStats, build_cross_game_results, build_team_stats,
                     compute_game_of_week)
from test_report_consistency import game


class FetchTests(unittest.TestCase):
    def test_transient_failure_retried(self):
        response=Mock()
        response.raise_for_status.return_value=None
        response.json.return_value=[]
        with patch.object(d.requests,'get',side_effect=[requests.Timeout(),response]) as get, patch.object(d.time,'sleep') as sleep, redirect_stdout(io.StringIO()):
            self.assertEqual(d._get('/games',{}),[])
        self.assertEqual(get.call_count,2)
        sleep.assert_called_once_with(2)

    def test_permanent_failure_not_retried(self):
        response=Mock(status_code=401)
        response.raise_for_status.side_effect=requests.HTTPError(response=response)
        with patch.object(d.requests,'get',return_value=response) as get, patch.object(d.time,'sleep') as sleep:
            with self.assertRaises(requests.HTTPError): d._get('/games',{})
        self.assertEqual(get.call_count,1)
        sleep.assert_not_called()

    def test_exhausted_retries_raise(self):
        with patch.object(d.requests,'get',side_effect=requests.Timeout()) as get, patch.object(d.time,'sleep'), redirect_stdout(io.StringIO()):
            with self.assertRaises(requests.Timeout): d._get('/games',{})
        self.assertEqual(get.call_count,d.HTTP_ATTEMPTS)

    def test_json_object_rejected(self):
        response=Mock()
        response.raise_for_status.return_value=None
        response.json.return_value={'error':'bad'}
        with patch.object(d.requests,'get',return_value=response):
            with self.assertRaises(ValueError): d._get('/games',{})

    def test_game_identity_and_schema_rejected(self):
        changes=({'season':2025},{'seasonType':'postseason'},{'completed':None},
                 {'homeConference':'ACC'},{'startDate':'2026-09-01'}, {'homePoints':-1},
                 {'homePoints':True},{'week':'1'}, {'homeTeam':''})
        for change in changes:
            with self.subTest(change=change), patch.object(d,'_get',return_value=[dict(game(1),**change)]):
                with self.assertRaises(ValueError): d.fetch_all_conference_games(2026,'SEC')

    def test_conflicting_game_duplicate_rejected(self):
        with patch.object(d,'_get',side_effect=[[game(1),dict(game(1),homePoints=42)],[]]):
            with self.assertRaisesRegex(ValueError,'Conflicting'): d.fetch_all_conference_games(2026,'SEC')

    def test_wrong_records_identity(self):
        for row in ({'year':2025,'conference':'SEC'},{'year':2026,'conference':'Big Ten'}):
            with patch.object(d,'_get',return_value=[row]):
                with self.assertRaises(ValueError): d.fetch_records(2026,'SEC')

    def test_wrong_poll_identity(self):
        with patch.object(d,'_get',return_value=[dict(season=2025,week=9,seasonType='regular',polls=[])]):
            with self.assertRaises(ValueError): d.fetch_rankings(2026,9)

    def test_unknown_or_fcs_polls_cannot_be_selected_as_fbs(self):
        for name in ('FCS Playoff Rankings','Not AP Top 25','FCS Coaches Poll'):
            self.assertEqual(d._poll_sort_key({'poll':name}),9)

    def test_postseason_poll_preferred_over_regular_larger_week(self):
        def entry(kind,week,school):
            return dict(season=2026,seasonType=kind,week=week,polls=[dict(poll='AP Top 25',ranks=[dict(school=school,rank=1)])])
        with patch.object(d,'_get',side_effect=[[entry('postseason',1,'Final')],[entry('regular',15,'Old')]]):
            ranks=d.fetch_rankings(2026,1,'postseason')
        self.assertEqual(ranks,{'Final':1})
        self.assertEqual(ranks.season_type,'postseason')

    def test_postseason_uses_last_regular_poll_if_not_published(self):
        entry=dict(season=2026,seasonType='regular',week=15,polls=[dict(poll='AP Top 25',ranks=[dict(school='S',rank=1)])])
        with patch.object(d,'_get',side_effect=[[],[entry]]):
            self.assertEqual(d.fetch_rankings(2026,1,'postseason').week,15)

    def test_rating_error_not_silently_swallowed(self):
        with patch.object(d,'_get',side_effect=requests.Timeout()):
            with self.assertRaises(requests.Timeout): d.fetch_sp_ratings(2026)

    def test_duplicate_or_wrong_season_ratings_rejected(self):
        for rows in ([dict(team='S',year=2025,rating=1)], [dict(team='S',year=2026,rating=1)]*2):
            with patch.object(d,'_get',return_value=rows):
                with self.assertRaises(ValueError): d.fetch_sp_ratings(2026)

    def test_provider_calendar_not_elapsed_week_guess(self):
        rows=[dict(season=2026,seasonType='regular',week=1,startDate='2026-08-29T07:00:00Z'),
              dict(season=2026,seasonType='regular',week=2,startDate='2026-09-08T07:00:00Z')]
        with patch.object(d,'_get',return_value=rows):
            self.assertEqual(d.get_current_period(now=datetime(2026,9,7,tzinfo=timezone.utc)),(1,'regular'))
            self.assertEqual(d.get_current_period(now=datetime(2026,9,8,7,tzinfo=timezone.utc)),(2,'regular'))

    def test_empty_calendar_rejected(self):
        with patch.object(d,'_get',return_value=[]):
            with self.assertRaises(ValueError): d.get_current_period()


class RenderingTests(unittest.TestCase):
    def test_tied_records_not_colored_as_a_loss(self):
        sec=ConferenceStats('SEC','SEC',[TeamStats('S','SEC',overall_wins=1,overall_losses=1)],h2h_wins=1,h2h_losses=1)
        big=ConferenceStats('Big Ten','Big Ten',[TeamStats('B','Big Ten',overall_wins=2,overall_losses=2)],h2h_wins=1,h2h_losses=1)
        html=_comparison_table_html(sec,big)
        self.assertNotIn('background:#c8f0c8',html)
        self.assertNotIn('background:#f7c5c5',html)

    def test_delivery_regenerates_stale_or_untrusted_narrative(self):
        cross=build_cross_game_results([game(1)])
        sec=ConferenceStats('SEC','SEC',h2h_wins=1)
        big=ConferenceStats('Big Ten','Big Ten',h2h_losses=1)
        subject,plain,html=build_email(sec,big,cross,'Big Ten leads 99-0','No games played',1,'SEC',2026)
        for body in (subject,plain,html):
            self.assertIn('SEC leads 1-0',body)
            self.assertNotIn('99-0',body)
            self.assertNotIn('No games played',body)

    def test_postseason_context_consistent_in_summary_and_email(self):
        sec=ConferenceStats('SEC','SEC')
        big=ConferenceStats('Big Ten','Big Ten')
        subject,plain,html=build_email(sec,big,[],None,'',1,'SEC',2026,season_type='postseason')
        self.assertIn('Postseason Wk 1',subject)
        for body in (plain,html):
            self.assertIn('Postseason Week 1',body)
            self.assertIn('report postseason week 1',body)

    def test_html_escapes_provider_team_names(self):
        sec=ConferenceStats('SEC','SEC',[TeamStats('<img src=x>','SEC')])
        big=ConferenceStats('Big Ten','Big Ten')
        _,_,html=build_email(sec,big,[],None,'',1,'SEC',2026)
        self.assertIn('&lt;img src=x&gt;',html)
        self.assertNotIn('<img src=x>',html)

    def test_upcoming_ignores_past_unplayed_and_missing_ratings(self):
        past=dict(game(1),completed=False,homePoints=None,awayPoints=None)
        future=dict(game(2),completed=False,homePoints=None,awayPoints=None,startDate='2026-12-01T12:00:00Z')
        cross=build_cross_game_results([past,future])
        now=datetime(2026,11,1,tzinfo=timezone.utc)
        self.assertIsNone(compute_game_of_week(cross,{},now))
        ratings={'SEC team':{'rating':0},'Big Ten team':{'rating':-1}}
        self.assertEqual(compute_game_of_week(cross,ratings,now).week,2)

    def test_missing_roster_team_rejected(self):
        rows=[dict(team='Other SEC',total={'wins':0,'losses':0},conferenceGames={'wins':0,'losses':0})]
        with self.assertRaisesRegex(ValueError,'roster'): build_team_stats(rows,[game(1)],{},{},'SEC')

    def test_postseason_results_follow_regular_season_and_are_labeled(self):
        raw=[dict(game(1),seasonType='postseason'),dict(game(15),seasonType='regular')]
        results=build_cross_game_results(raw)
        self.assertEqual([g.period_label for g in results],['15','Post 1'])

    def test_invalid_mail_rejected_before_gmail_auth(self):
        with patch('email_builder.get_gmail_service') as gmail:
            for recipients in ([],['bad'],['user@example.com\nBcc: other@example.com']):
                with self.assertRaises(ValueError): send_gmail('sender@example.com',recipients,'subject','text','html')
            with self.assertRaises(ValueError): send_gmail('sender@example.com',['user@example.com'],'a\nb','text','html')
            gmail.assert_not_called()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'history.db'
        self.patch=patch.object(db,'DB_PATH',str(self.path))
        self.patch.start()
        self.sec=ConferenceStats('SEC','SEC')
        self.big=ConferenceStats('Big Ten','Big Ten')
        self.pair=[('SEC',self.sec),('Big Ten',self.big)]

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_read_does_not_create_database(self):
        self.assertIsNone(db.load_prior_snapshot(2026,10,'SEC'))
        self.assertFalse(self.path.exists())

    def test_legacy_history_preserved_and_not_compared(self):
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('CREATE TABLE weekly_snapshots (evidence TEXT)')
            c.execute("INSERT INTO weekly_snapshots VALUES ('legacy untouched')")
        db.init_db()
        self.assertIsNone(db.load_prior_snapshot(2026,10,'SEC'))
        with closing(sqlite3.connect(self.path)) as c, c:
            self.assertEqual(c.execute('SELECT * FROM weekly_snapshots').fetchall(),[('legacy untouched',)])

    def test_pair_saved_together_and_unavailable_rank_count_null(self):
        db.init_db()
        db.save_snapshots(2026,9,self.pair)
        with closing(sqlite3.connect(self.path)) as c, c:
            rows=c.execute('SELECT saved_at,ranked_teams FROM report_snapshots').fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][0],rows[1][0])
        self.assertIsNone(rows[0][1])

    def test_second_save_failure_rolls_back_both_rows(self):
        db.init_db()
        original=db._save
        def failing(c,year,week,name,*args):
            if name=='Big Ten': raise RuntimeError('injected second-row failure')
            return original(c,year,week,name,*args)
        with patch.object(db,'_save',side_effect=failing):
            with self.assertRaises(RuntimeError): db.save_snapshots(2026,9,self.pair)
        with closing(sqlite3.connect(self.path)) as c, c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM report_snapshots').fetchone()[0],0)

    def test_postseason_week_one_does_not_overwrite_regular_week_one(self):
        db.init_db()
        db.save_snapshots(2026,1,self.pair)
        db.save_snapshots(2026,15,self.pair)
        db.save_snapshots(2026,1,self.pair,'postseason')
        with closing(sqlite3.connect(self.path)) as c, c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM report_snapshots').fetchone()[0],6)
        prior=db.load_prior_snapshot(2026,1,'SEC','postseason')
        self.assertEqual((prior['season_type'],prior['week']),('regular',15))
        prior=db.load_prior_snapshot(2026,2,'SEC','postseason')
        self.assertEqual((prior['season_type'],prior['week']),('postseason',1))


class RunnerTests(unittest.TestCase):
    def data(self):
        g=game(1)
        def record(team,wins,losses):
            return dict(team=team,total=dict(wins=wins,losses=losses),conferenceGames=dict(wins=0,losses=0))
        return dict(sec_records=[record('SEC team',1,0)],big10_records=[record('Big Ten team',0,1)],
                    sec_all_games=[g],big10_all_games=[g],cross_games=[g],rankings=d.Rankings(),sp_ratings={})

    def test_dry_run_never_sends_or_writes_snapshots(self):
        with patch('sys.argv',['secevaluator','--dry-run','--week','9']), patch.object(app,'in_season',return_value=True), patch.object(app,'fetch_all_data',return_value=self.data()), patch.object(app,'load_prior_snapshot',return_value=None), patch.object(app,'init_db') as init, patch.object(app,'send_gmail') as send, patch.object(app,'save_snapshots') as save, patch.object(app,'log'), redirect_stdout(io.StringIO()):
            app.main()
        init.assert_not_called()
        send.assert_not_called()
        save.assert_not_called()

    def test_test_mode_without_recipients_aborts_before_fetch_or_db(self):
        with patch('sys.argv',['secevaluator','--test']), patch.object(app,'TEST_TO_EMAILS',[]), patch.object(app,'in_season',return_value=True), patch.object(app,'fetch_all_data') as fetch, patch.object(app,'init_db') as init, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): app.main()
        fetch.assert_not_called()
        init.assert_not_called()

    def test_bad_data_never_sends(self):
        data=self.data()
        data['sec_records'][0]['total']['wins']=2
        with patch('sys.argv',['secevaluator','--dry-run','--week','9']), patch.object(app,'in_season',return_value=True), patch.object(app,'fetch_all_data',return_value=data), patch.object(app,'send_gmail') as send, patch.object(app,'log'):
            with self.assertRaises(ValueError): app.main()
        send.assert_not_called()

    def test_successful_production_path_saves_pair_after_mocked_send(self):
        events=[]
        with patch('sys.argv',['secevaluator','--week','9']), patch.object(app,'TEST_TO_EMAILS',[]), patch.object(app,'SENDER_EMAIL','sender@example.com'), patch.object(app,'RECIPIENTS',['reader@example.com']), patch.object(app,'in_season',return_value=True), patch.object(app,'fetch_all_data',return_value=self.data()), patch.object(app,'load_prior_snapshot',return_value=None), patch.object(app,'init_db'), patch.object(app,'log'), patch.object(app,'send_gmail',side_effect=lambda *args: events.append('send')), patch.object(app,'save_snapshots',side_effect=lambda *args: events.append('save')):
            app.main()
        self.assertEqual(events,['send','save'])

    def test_test_mode_sends_only_mock_test_recipient_without_db_writes(self):
        with patch('sys.argv',['secevaluator','--week','9','--test']), patch.object(app,'TEST_TO_EMAILS',['test@example.com']), patch.object(app,'SENDER_EMAIL','sender@example.com'), patch.object(app,'in_season',return_value=True), patch.object(app,'fetch_all_data',return_value=self.data()), patch.object(app,'load_prior_snapshot',return_value=None), patch.object(app,'init_db') as init, patch.object(app,'log'), patch.object(app,'send_gmail') as send, patch.object(app,'save_snapshots') as save:
            app.main()
        self.assertEqual(send.call_args.args[1],['test@example.com'])
        init.assert_not_called()
        save.assert_not_called()

    def test_failed_send_does_not_save(self):
        with patch('sys.argv',['secevaluator','--week','9']), patch.object(app,'TEST_TO_EMAILS',[]), patch.object(app,'SENDER_EMAIL','sender@example.com'), patch.object(app,'in_season',return_value=True), patch.object(app,'fetch_all_data',return_value=self.data()), patch.object(app,'load_prior_snapshot',return_value=None), patch.object(app,'init_db'), patch.object(app,'log'), patch.object(app,'send_gmail',side_effect=RuntimeError('mock failure')), patch.object(app,'save_snapshots') as save:
            with self.assertRaises(SystemExit): app.main()
        save.assert_not_called()

if __name__=='__main__': unittest.main()
