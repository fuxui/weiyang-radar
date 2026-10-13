import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('radar', ROOT / 'server.py')
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)


class RadarTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.test-work'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.old_root, self.old_db = radar.ROOT, radar.DB
        radar.ROOT = Path(self.tmp.name)
        radar.DB = radar.ROOT / 'radar.sqlite3'
        radar.conn().close()

    def tearDown(self):
        radar.ROOT, radar.DB = self.old_root, self.old_db
        self.tmp.cleanup()

    def require(self, name):
        self.assertTrue(callable(getattr(radar, name, None)), name + ' 尚未实现')

    def add(self):
        self.require('add_news')
        return radar.add_news({'title': 'AI 工具需求', 'link': 'https://example.org/a',
                               'source': '人工录入', 'category': '前沿科技'})

    def test_database_not_downloadable(self):
        http = radar.ThreadingHTTPServer(('127.0.0.1', 0), radar.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            try:
                response = urlopen('http://127.0.0.1:%s/radar.sqlite3' % http.server_port)
                status = response.status
                response.close()
            except HTTPError as ex:
                status = ex.code
            self.assertEqual(status, 404)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_dedup_ignores_tracking(self):
        ident = self.add()
        self.assertEqual(ident, radar.add_news({'title': '更新标题', 'link': 'https://example.org/a?utm_source=x', 'source': '其他'}))
        self.assertEqual(len(radar.state()['news']), 1)

    def test_atom_selects_alternate_not_self(self):
        self.require('parse_feed')
        data = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Hello</title><link rel="self" href="https://x.org/feed/1"/><link rel="alternate" href="https://x.org/article"/><updated>2026-01-01T00:00:00Z</updated></entry></feed>'
        self.assertEqual(radar.parse_feed(data)[0]['link'], 'https://x.org/article')

    def test_html_doctype_in_cdata_is_not_xml_entity(self):
        self.require('parse_feed')
        data=b'<rss><item><title>Test</title><link>https://example.org/news</link><description><![CDATA[<!DOCTYPE html><p>Article example</p>]]></description></item></rss>'
        self.assertEqual(len(radar.parse_feed(data)),1)

    def test_verification_requires_evidence_and_logs(self):
        ident = self.add()
        self.require('verify_news')
        with self.assertRaises(ValueError):
            radar.verify_news({'id': ident, 'status': 'verified', 'note': ''})
        radar.verify_news({'id': ident, 'status': 'verified', 'note': '对照发布方原文确认时间与内容', 'evidence': 'https://example.org/original'})
        self.assertEqual(radar.state()['news'][0]['status'], 'verified')
        self.assertTrue(radar.state()['audit'])

    def test_legacy_verified_does_not_bypass_evidence(self):
        self.require('import_legacy')
        radar.import_legacy([{'id':'old', 'title':'旧素材','verified':True,'source':'https://example.org','notes':'笔记','scores':[3]*5}])
        self.assertEqual(radar.state()['news'][0]['status'], 'pending')
        self.assertEqual(len(radar.state()['research']), 1)

    def test_import_transaction_rejects_partial_invalid(self):
        self.require('import_legacy')
        with self.assertRaises(ValueError):
            radar.import_legacy([{'id':'one','title':'有效','scores':[3]*5}, {'id':'two','title':'无效','scores':[99]*5}])
        self.assertFalse(radar.state()['news'])

    def test_opportunity_high_score_requires_customer_evidence(self):
        ident = self.add()
        self.require('save_research')
        result = radar.save_research({'news_id': ident, 'scores':[5]*5, 'customer':'开发者','pain':'整理资料慢','experiment':'访谈3人','budget':0})
        self.assertEqual(result['stage'], '待验证')
        result = radar.save_research({'news_id': ident, 'scores':[5]*5, 'customer':'开发者','pain':'整理资料慢','experiment':'访谈3人','budget':0,'payment_evidence':'访谈记录：两人愿付20元','competition':'已有手工替代','risk':'数据授权'})
        self.assertEqual(result['stage'], '可做小实验')

    def test_claim_requires_counterexample_for_review(self):
        ident = self.add()
        self.require('save_research')
        with self.assertRaises(ValueError):
            radar.save_research({'news_id':ident, 'claim':'所有人都会用AI', 'confidence':101})
        result = radar.save_research({'news_id':ident, 'claim':'流程会缩短','confidence':60,'counter':'用户不愿上传数据','falsifier':'10次实验没有节约时间'})
        self.assertEqual(result['confidence'], 60)

    def test_approval_and_edit_invalidation(self):
        ident = self.add()
        self.require('save_draft')
        draft = radar.save_draft({'news_id':ident,'body':'一个待核实的判断'})
        with self.assertRaises(ValueError):
            radar.approve_draft({'id':draft['id'], 'human':True})
        radar.verify_news({'id':ident,'status':'verified','note':'核对原文','evidence':'https://example.org/a'})
        body = '事实：工具已发布。推断：可能节约时间。反例：隐私需求限制使用。'
        draft = radar.save_draft({'id':draft['id'],'news_id':ident,'body':body,'counter':'隐私限制','risk':'不保证效果'})
        approved = radar.approve_draft({'id':draft['id'],'human':True})
        self.assertEqual(approved['status'], 'approved')
        edited = radar.save_draft({'id':draft['id'],'news_id':ident,'body':'改稿'})
        self.assertEqual(edited['status'], 'draft')

    def test_english_draft_labels_are_accepted(self):
        ident = self.add()
        radar.verify_news({'id':ident,'status':'verified','note':'Checked the original source','evidence':'https://example.org/a'})
        draft = radar.save_draft({'news_id':ident,'body':'Fact: A benchmark was introduced.\nInference: It may help evaluate tools.',
                                  'counter':'Results may not transfer.','risk':'Not independently reproduced.'})
        self.assertTrue(radar.state()['drafts'][0]['review']['ready'])

    def test_retracted_news_invalidates_approved_draft(self):
        ident = self.add()
        self.require('save_draft')
        radar.verify_news({'id':ident,'status':'verified','note':'核对原文','evidence':'https://example.org/a'})
        draft = radar.save_draft({'news_id':ident,'body':'事实：已发布。推断：效果待检验。','counter':'可能无效','risk':'样本不足'})
        radar.approve_draft({'id':draft['id'],'human':True})
        radar.verify_news({'id':ident,'status':'disputed','note':'原文更正'})
        self.assertNotEqual(radar.state()['drafts'][0]['status'], 'approved')

    def test_market_requires_time_and_source(self):
        self.require('save_market')
        with self.assertRaises(ValueError):
            radar.save_market({'symbol':'AAPL', 'price':100})
        with self.assertRaises(ValueError):
            radar.save_market({'symbol':'AAPL','price':float('nan'),'observed_at':'2026-01-01T00:00:00Z','source':'https://example.org'})
        quote = radar.save_market({'symbol':'AAPL','price':100,'observed_at':'2026-01-01T00:00:00Z','source':'https://example.org','kind':'股票','currency':'USD'})
        self.assertEqual(quote['price'],100)
        self.assertTrue(quote['stale'])

    def test_v1_schema_migration_preserves_rows(self):
        self.require('state')
        with radar.conn() as c:
            c.execute('DROP TABLE news')
            c.execute('CREATE TABLE news (id TEXT PRIMARY KEY,title TEXT,link TEXT,source TEXT,published TEXT,category TEXT,summary TEXT,verified INTEGER DEFAULT 0,saved_at TEXT)')
            c.execute("INSERT INTO news VALUES ('old','旧新闻','https://example.org','旧源','','其他','',1,'2026-01-01')")
        radar.conn().close()
        self.assertEqual(radar.state()['news'][0]['id'],'old')
        self.assertEqual(radar.state()['news'][0]['status'],'pending')


if __name__ == '__main__':
    unittest.main()
