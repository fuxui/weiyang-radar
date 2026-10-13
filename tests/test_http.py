import json
import http.client
import sqlite3
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from test_radar import radar, ROOT


class HttpTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.test-work'
        scratch.mkdir(parents=True,exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.old_db = radar.DB
        radar.DB = ROOT.__class__(self.tmp.name) / 'radar.sqlite3'
        radar.conn().close()
        self.http = radar.ThreadingHTTPServer(('127.0.0.1',0),radar.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.http.server_port)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        radar.DB = self.old_db
        self.tmp.cleanup()

    def request(self,path,body=None,headers=None):
        try:
            req = Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                          headers=headers or {})
            with urlopen(req,timeout=5) as response:
                return response.status,response.read(),response.headers
        except HTTPError as ex:
            return ex.code,ex.read(),ex.headers

    def test_csrf_and_host_rejected(self):
        self.assertEqual(self.request('/api/news',{'title':'bad'})[0],403)
        headers={'X-Radar-Client':'local','Origin':'https://evil.example'}
        self.assertEqual(self.request('/api/news',{'title':'bad'},headers)[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertFalse(radar.state()['news'])

    def test_private_proxy_origin_is_opt_in_and_exact(self):
        public = 'https://my-pc.private.ts.net:8443'
        headers = {'Host':'my-pc.private.ts.net:8443','Origin':public,'X-Radar-Client':'local'}
        with patch.dict(radar.os.environ,{},clear=True):
            self.assertEqual(self.request('/api/state',headers=headers)[0],403)
        with patch.dict(radar.os.environ,{'RADAR_PRIVATE_ORIGIN':public},clear=True):
            self.assertEqual(self.request('/api/state',headers=headers)[0],200)
            self.assertEqual(self.request('/api/news',{'title':'私人测试'},headers)[0],200)
            self.assertEqual(self.request('/api/state',headers={**headers,'Host':'other.private.ts.net:8443'})[0],403)
            self.assertEqual(self.request('/api/news',{'title':'bad'},{**headers,'Origin':'https://evil.example'})[0],403)

    def test_public_origin_must_be_private_https_domain(self):
        with patch.dict(radar.os.environ,{'RADAR_PRIVATE_ORIGIN':'https://evil.example'},clear=True):
            self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)

    def test_home_screen_icon_and_manifest(self):
        status,blob,headers=self.request('/radar-icon-192.png')
        self.assertEqual(status,200)
        self.assertEqual(headers['Content-Type'],'image/png')
        self.assertTrue(blob.startswith(b'\x89PNG'))
        status,blob,headers=self.request('/manifest.webmanifest')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(blob)['start_url'],'/')
        self.assertEqual(headers['Content-Type'],'application/manifest+json')

    def test_lan_login_protects_data_and_allows_authenticated_work(self):
        radar.configure_lan(self.http,'192.168.1.5','0123456789')
        self.assertEqual(self.request('/api/state')[0],401)
        self.assertEqual(self.request('/api/backup')[0],401)
        self.assertIn('手机连接'.encode(),self.request('/')[1])
        headers={'Host':'192.168.1.5:'+str(self.http.server_port),'Origin':'http://192.168.1.5:'+str(self.http.server_port)}
        self.assertEqual(self.request('/api/state',headers=headers)[0],401)
        c = http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        try:
            c.request('POST','/login','pin=0123456789',headers={**headers,'Content-Type':'application/x-www-form-urlencoded'})
            response=c.getresponse()
            response.read()
            self.assertEqual(response.status,303)
            cookie=response.getheader('Set-Cookie')
        finally:
            c.close()
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=Strict',cookie)
        auth={**headers,'Cookie':cookie.split(';')[0],'X-Radar-Client':'local'}
        self.assertEqual(self.request('/api/news',{'title':'手机研究'},auth)[0],200)
        self.assertEqual(self.request('/api/state',headers=auth)[0],200)
        self.assertEqual(self.request('/api/news',{'title':'bad'},{**auth,'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/state',headers={**auth,'Cookie':'radar_lan=bad'})[0],401)

    def test_lan_wrong_pin_rate_limit_and_no_public_address(self):
        with self.assertRaises(ValueError):
            radar.configure_lan(self.http,'8.8.8.8','0123456789')
        radar.configure_lan(self.http,'192.168.1.5','0123456789')
        for _ in range(5):
            self.assertEqual(self.request('/login','ignored')[0],403)
        self.assertEqual(self.request('/login','ignored')[0],429)

    def test_lan_origin_and_auth_must_both_match(self):
        radar.configure_lan(self.http,'192.168.1.5','0123456789')
        self.assertEqual(self.request('/login',{'pin':'0123456789'},{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/style.css')[0],200)
        self.assertEqual(self.request('/server.py')[0],401)

    def test_full_http_workflow_and_backup(self):
        headers={'X-Radar-Client':'local','Content-Type':'application/json'}
        status,body,_ = self.request('/api/news',{'title':'真实观察','link':'https://example.org/evidence'},headers)
        self.assertEqual(status,200)
        ident=json.loads(body)['id']
        self.assertEqual(self.request('/api/verify',{'id':ident,'status':'verified','note':'核对原文','evidence':'https://example.org/evidence'},headers)[0],200)
        self.assertEqual(self.request('/api/template',{'news_id':ident},headers)[0],200)
        status,blob,_=self.request('/api/backup')
        self.assertEqual(status,200)
        self.assertTrue(blob.startswith(b'SQLite format 3'))
        backup=radar.ROOT.__class__(self.tmp.name)/'restored.sqlite3'
        backup.write_bytes(blob)
        c=sqlite3.connect(backup)
        try:
            self.assertEqual(c.execute('SELECT count(*) FROM news').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM drafts').fetchone()[0],1)
        finally:
            c.close()

    def test_static_allowlist_and_malformed_request(self):
        self.assertEqual(self.request('/')[0],200)
        self.assertEqual(self.request('/server.py')[0],404)
        self.assertEqual(self.request('/../server.py')[0],404)
        self.assertEqual(self.request('/api/news',[],{'X-Radar-Client':'local'})[0],400)
        self.assertEqual(self.request('/api/refresh')[0],404)

    def test_csv_formula_is_text(self):
        radar.add_news({'title':'=HYPERLINK("evil")'})
        self.assertIn("'=HYPERLINK",self.request('/api/export.csv')[1].decode('utf-8'))

    def test_feed_failure_preserves_saved_news(self):
        radar.add_news({'title':'原有资料'})
        with patch.object(radar,'fetch_bytes',side_effect=TimeoutError('offline')):
            result=radar.refresh()
        self.assertTrue(all(not s['ok'] for s in result['sources']))
        self.assertEqual(len(radar.state()['news']),1)

    def test_feed_reports_duplicates_without_overwriting_verification(self):
        ident=radar.add_news({'title':'原有标题','link':'https://example.org/a'})
        radar.verify_news({'id':ident,'status':'verified','evidence':'https://example.org/a','note':'已核对原文'})
        payload=b'<rss><channel><item><title>Changed</title><link>https://example.org/a?utm_source=feed</link></item><item><title>New</title><link>https://example.org/b</link></item></channel></rss>'
        with patch.object(radar,'fetch_bytes',return_value=payload):
            result=radar.collect_feed(radar.FEEDS[0])
        self.assertTrue(result['ok'])
        self.assertEqual(result['items'],2)
        self.assertEqual(result['added'],1)
        self.assertEqual(result.get('duplicates'),1)
        old=next(n for n in radar.state()['news'] if n['id']==ident)
        self.assertEqual(old['title'],'原有标题')
        self.assertEqual(old['status'],'verified')

    def test_feed_recovers_from_transient_timeout(self):
        payload=b'<rss><channel><item><title>New</title><link>https://example.org/a</link></item></channel></rss>'
        with patch.object(radar,'fetch_bytes',side_effect=[URLError(TimeoutError('handshake timed out')),payload]):
            result=radar.collect_feed(radar.FEEDS[0])
        self.assertTrue(result['ok'])
        self.assertEqual(result['added'],1)
        self.assertEqual(result.get('attempts'),2)
        self.assertEqual(len(radar.state()['news']),1)

    def test_feed_does_not_retry_http_403(self):
        with patch.object(radar,'fetch_bytes',side_effect=HTTPError('https://example.org',403,'Forbidden',{},None)) as fetch:
            result=radar.collect_feed(radar.FEEDS[0])
        self.assertFalse(result['ok'])
        self.assertEqual(fetch.call_count,1)
        self.assertIn('403',result.get('error_summary',''))

    def test_feed_retry_is_bounded_and_explains_timeout(self):
        with patch.object(radar,'fetch_bytes',side_effect=TimeoutError('handshake timed out')) as fetch:
            result=radar.collect_feed(radar.FEEDS[0])
        self.assertFalse(result['ok'])
        self.assertEqual(fetch.call_count,2)
        self.assertIn('超时',result.get('error_summary',''))

    def test_ai_not_configured_and_consent_required(self):
        with patch.dict(radar.os.environ,{},clear=True):
            with self.assertRaises(ValueError):
                radar.ai_draft({'news_id':'x','consent':True})
        with patch.dict(radar.os.environ,{'RADAR_AI_BASE_URL':'http://127.0.0.1:1234/v1','RADAR_AI_MODEL':'test'},clear=True):
            with self.assertRaises(ValueError):
                radar.ai_draft({'news_id':'x'})

    def test_ai_response_stays_unapproved(self):
        ident=radar.add_news({'title':'工具发布'})
        payload=json.dumps({'choices':[{'message':{'content':'事实：尚待核实。推断：效果待验证。'}}]}).encode()
        with patch.dict(radar.os.environ,{'RADAR_AI_BASE_URL':'http://127.0.0.1:1234/v1','RADAR_AI_MODEL':'fixture'},clear=True):
            with patch.object(radar,'fetch_bytes',return_value=payload):
                result=radar.ai_draft({'news_id':ident,'consent':True})
        self.assertEqual(result['status'],'draft')
        self.assertEqual(radar.state()['news'][0]['status'],'pending')

    def test_market_draft_needs_fresh_time(self):
        ident=radar.add_news({'title':'股票观察','category':'股市与公司','link':'https://example.org'})
        radar.verify_news({'id':ident,'status':'verified','evidence':'https://example.org','note':'核对价格'})
        draft=radar.save_draft({'news_id':ident,'body':'事实：来源已核对。推断：仍不确定。','counter':'样本少','risk':'价格波动'})
        with self.assertRaises(ValueError):
            radar.approve_draft({'id':draft['id'],'human':True})

    def test_xml_entities_and_unsafe_links_rejected(self):
        with self.assertRaises(ValueError):
            radar.parse_feed(b'<!DOCTYPE foo><rss/>')
        self.assertEqual(radar.parse_feed(b'<rss><item><title>bad</title><link>javascript:alert(1)</link></item></rss>'),[])

    def test_ai_key_never_in_state(self):
        with patch.dict(radar.os.environ,{'RADAR_AI_KEY':'secret-fixture'}):
            self.assertNotIn('secret-fixture',json.dumps(radar.state()))

    def test_market_classification(self):
        self.assertTrue(callable(getattr(radar,'classify',None)),'关键词分类应保留')
        self.assertEqual(radar.classify('Bitcoin price volatility','前沿科技'),'加密货币')
        self.assertEqual(radar.classify('AAPL stock earnings','前沿科技'),'股市与公司')

if __name__=='__main__':
    unittest.main()
