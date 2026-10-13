import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from test_radar import radar, ROOT


class ChineseNewsTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-work').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.test-work')
        self.old_db = radar.DB
        radar.DB = Path(self.tmp.name) / 'radar.sqlite3'
        radar.conn().close()
        self.at = datetime(2026, 10, 11, 3, tzinfo=timezone.utc)

    def tearDown(self):
        radar.DB = self.old_db
        self.tmp.cleanup()

    def test_beijing_midnight_boundary(self):
        self.assertEqual(radar.publication_info('2026-10-10T15:59:59Z', self.at)['date_status'], 'history')
        info = radar.publication_info('2026-10-10T16:00:00Z', self.at)
        self.assertEqual(info['published_day'], '2026-10-11')
        self.assertEqual(info['date_status'], 'today')

    def test_36kr_explicit_timezone_date(self):
        info = radar.publication_info('2026-10-11 10:00:00  +0800', self.at)
        self.assertEqual(info['published_at'], '2026-10-11T02:00:00+00:00')
        self.assertEqual(info['date_status'], 'today')

    def test_unknown_or_naive_date_never_becomes_today(self):
        for value in ('', 'bad date', '2026-10-11 10:00:00'):
            self.assertEqual(radar.publication_info(value, self.at)['date_status'], 'unknown')
        self.assertEqual(radar.publication_info('2026-10-11T04:00:00Z', self.at)['date_status'], 'future')

    def test_today_selected_before_feed_limit(self):
        entries = ''.join('<item><title>old</title><link>https://example.org/old%s</link><pubDate>2026-10-01T00:00:00Z</pubDate></item>' % i for i in range(90))
        entries += '<item><title>today</title><link>https://example.org/today</link><pubDate>2026-10-11T02:00:00Z</pubDate></item>'
        with patch.object(radar, 'fetch_bytes', return_value=('<rss>'+entries+'</rss>').encode()), patch.object(radar, 'now', return_value=self.at.isoformat()):
            result = radar.collect_feed(dict(radar.FEEDS[0], limit=10))
        self.assertTrue(result['ok'])
        self.assertEqual(result['available'], 91)
        self.assertEqual(result['items'], 10)
        self.assertEqual(result['today_items'], 1)
        self.assertTrue(any(n['title']=='today' for n in radar.state()['news']))

    def test_newly_saved_old_news_does_not_outrank_today(self):
        with patch.object(radar, 'now', return_value=self.at.isoformat()):
            radar.add_news({'title':'今日中文科技','source':'IT之家','published':'2026-10-11T01:00:00Z','category':'前沿科技'})
            radar.add_news({'title':'旧新闻','published':'2026-08-01T02:00:00Z'})
            radar.add_news({'title':'日期未知'})
            state = radar.state()
        self.assertEqual(state['today'], '2026-10-11')
        self.assertEqual(state['news'][0]['title'], '今日中文科技')
        self.assertEqual(state['news'][0]['language'], 'zh')
        self.assertEqual(state['news'][-1]['date_status'], 'unknown')
        self.assertTrue(all(n['status']=='pending' for n in state['news']))

    def test_today_chinese_priority_and_original_date_retained(self):
        with patch.object(radar, 'now', return_value=self.at.isoformat()):
            radar.add_news({'title':'New tool','source':'GitHub Blog','published':'2026-10-11T02:30:00Z','category':'前沿科技'})
            radar.add_news({'title':'中文工具','source':'IT之家','published':'Sun, 11 Oct 2026 01:00:00 GMT','category':'前沿科技'})
            state = radar.state()
        self.assertEqual(state['news'][0]['title'], '中文工具')
        self.assertEqual(state['news'][0]['published'], 'Sun, 11 Oct 2026 01:00:00 GMT')

    def test_six_publishers_and_crypto_context(self):
        chinese = [f for f in radar.FEEDS if f.get('language')=='zh' and f['type']=='媒体报道']
        self.assertGreaterEqual(len(chinese), 6)
        self.assertEqual(radar.FEEDS[0]['language'], 'zh')
        self.assertIn('when%3A1d', next(f['url'] for f in radar.FEEDS if f['id']=='google'))
        self.assertEqual(radar.classify('BTC与Web3项目融资'), '加密货币')
        payload=b'<rss><item><title>AI earnings</title><link>https://example.org/crypto</link></item></rss>'
        with patch.object(radar, 'fetch_bytes', return_value=payload):
            result = radar.collect_feed(next(f for f in radar.FEEDS if f['id']=='odaily'))
        self.assertTrue(result['ok'])
        self.assertEqual(radar.state()['news'][0]['category'], '加密货币')


if __name__=='__main__':
    unittest.main()
