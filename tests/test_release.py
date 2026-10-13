import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from test_radar import radar, ROOT


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = radar.DB
        radar.DB = Path(self.tmp.name) / 'test.sqlite3'
        radar.conn().close()

    def tearDown(self):
        radar.DB = self.old_db
        self.tmp.cleanup()

    def test_import_counts_actual_new_rows_and_duplicates(self):
        items = [{'title':'合成工具观察','link':'https://example.invalid/demo','category':'前沿科技','notes':'教学样例'}]
        result = radar.import_legacy(items)
        self.assertEqual(result.get('added'),1)
        self.assertEqual(result.get('duplicates'),0)
        self.assertEqual(result.get('research_added'),1)
        ident = radar.state()['news'][0]['id']
        radar.verify_news({'id':ident,'status':'verified','evidence':'https://example.invalid/evidence','note':'仅测试记录'})
        radar.save_research({'news_id':ident,'notes':'用户新笔记'})
        result = radar.import_legacy(items + items)
        self.assertEqual(result.get('processed'),2)
        self.assertEqual(result.get('added'),0)
        self.assertEqual(result.get('duplicates'),2)
        self.assertEqual(result.get('research_added'),0)
        self.assertEqual(radar.state()['news'][0]['status'],'verified')
        self.assertEqual(radar.state()['research'][0]['notes'],'用户新笔记')

    def test_empty_import_does_not_create_audit_or_research(self):
        result = radar.import_legacy([])
        self.assertEqual(result.get('added'),0)
        self.assertEqual(result.get('duplicates'),0)
        self.assertEqual(radar.state()['audit'],[])
        self.assertEqual(radar.state()['research'],[])

    def test_import_returns_unique_batch_ids_including_existing_rows(self):
        first={'title':'历史样例','link':'https://example.invalid/first'}
        second={'title':'日期未知样例','link':'https://example.invalid/second'}
        old=radar.add_news(first)
        result=radar.import_legacy([first,second,second])
        self.assertEqual(result.get('ids'),[old,radar.news_data(second)['id']])
        self.assertEqual(result['added'],1)

    def test_invalid_import_is_atomic(self):
        with self.assertRaises(ValueError):
            radar.import_legacy([{'title':'有效'}, {'title':'无效','scores':[99]*5}])
        self.assertEqual(radar.state()['news'],[])

    def draft(self):
        ident=radar.add_news({'title':'合成研究','link':'https://example.invalid/demo','category':'前沿科技'})
        draft=radar.save_draft({'news_id':ident,'body':'事实：仅教学数据。推断：值得验证。','counter':'样本有限','risk':'不能推广到真实世界'})
        return ident,draft

    def test_draft_export_downloads_saved_content_with_review_status(self):
        ident,draft=self.draft()
        self.assertTrue(callable(getattr(radar,'export_draft',None)),'需要本地草稿导出')
        result=radar.export_draft(draft['id']).decode('utf-8')
        self.assertIn('待审核',result)
        self.assertIn('修订：1',result)
        self.assertIn(draft['body'],result)
        self.assertIn('不能推广到真实世界',result)
        self.assertIn('不会自动发布',result)
        self.assertIn('https://example.invalid/demo',result)
        radar.verify_news({'id':ident,'status':'verified','evidence':'https://example.invalid/evidence','note':'教学核实记录'})
        radar.approve_draft({'id':draft['id'],'human':True})
        self.assertIn('人工审核通过',radar.export_draft(draft['id']).decode('utf-8'))
        radar.verify_news({'id':ident,'status':'disputed','note':'教学撤回'})
        exported=radar.export_draft(draft['id']).decode('utf-8')
        self.assertIn('需要重新审核',exported)
        self.assertNotIn('审核状态：人工审核通过',exported)

    def test_unknown_draft_export_is_clear_error(self):
        self.assertTrue(callable(getattr(radar,'export_draft',None)),'需要本地草稿导出')
        with self.assertRaisesRegex(ValueError,'草稿不存在'):
            radar.export_draft('missing')

    def test_draft_export_http_attachment_and_missing_id(self):
        _,draft=self.draft()
        http=radar.ThreadingHTTPServer(('127.0.0.1',0),radar.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True)
        thread.start()
        base='http://127.0.0.1:'+str(http.server_port)
        try:
            with urlopen(base+'/api/draft/export?id='+draft['id']) as response:
                self.assertEqual(response.status,200)
                self.assertIn('attachment',response.headers['Content-Disposition'])
                self.assertIn('.md',response.headers['Content-Disposition'])
                self.assertIn(draft['body'],response.read().decode('utf-8'))
            with self.assertRaises(HTTPError) as err:
                urlopen(base+'/api/draft/export?id=missing')
            self.assertEqual(err.exception.code,404)
        finally:
            http.shutdown();http.server_close();thread.join()


if __name__=='__main__':
    unittest.main()
