import concurrent.futures
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

spec=importlib.util.spec_from_file_location('geotrace',Path(__file__).resolve().parents[1]/'app.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();app.DB=Path(cls.tmp.name)/'test.sqlite3';app.init_db()
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def request(self,path,data=None):
        req=urllib.request.Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req) as res:
                raw=res.read();return res.status,json.loads(raw) if res.headers.get_content_type()=='application/json' else raw
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def create(self,**kw):
        data=dict(site='Участок',profile='ПР-01',point='001',material='Почва');data.update(kw)
        status,s=self.request('/api/samples',data);self.assertEqual(status,201);return s
    def test_health_and_database_error_response(self):
        status,health=self.request('/api/health')
        self.assertEqual(status,200);self.assertEqual(health['version'],app.APP_VERSION)
        with patch.object(app,'connection',side_effect=sqlite3.OperationalError('database is locked')):
            status,body=self.request('/api/samples',dict(site='test',profile='1',point='1',material='soil'))
        self.assertEqual(status,503);self.assertIn('database is locked',body['error'])

    def test_lifecycle_and_results(self):
        s=self.create();url=f'/api/samples/{s["id"]}'
        self.assertEqual(self.request(url+'/status',{'status':3})[0],400)
        for stage in (1,2,3):self.assertEqual(self.request(url+'/status',{'status':stage})[0],200)
        self.assertEqual(self.request(url+'/status',{'status':4})[0],400)
        for value in (-1,'NaN','Infinity'):
            self.assertEqual(self.request(url+'/results',dict(element='Cu',value=value,unit='мг/кг',method='ICP-MS'))[0],400)
        self.assertEqual(self.request(url+'/results',dict(element='Cu',value=42.5,unit='мг/кг',method='ICP-MS'))[0],200)
        self.assertEqual(self.request(url+'/results',dict(element='Au',value=0.01,unit='г/т',method='ICP-MS',qualifier='<'))[0],200)
        status,done=self.request(url+'/status',{'status':4});self.assertEqual(status,200)
        self.assertEqual(len(done['events']),5);self.assertEqual(len(done['results']),2)
        app.init_db();persisted=self.request(url)[1];self.assertEqual(persisted['status'],4)
        self.assertEqual(self.request(url+'/results',dict(element='Cu',value=1,unit='мг/кг',method='ICP-MS'))[0],400)
        csv=self.request('/api/export')[1].decode('utf-8-sig');self.assertIn('42.5',csv);self.assertIn('ICP-MS',csv)
    def test_numbering_and_coordinates(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.create(),range(8)))
        self.assertEqual(len({s['code'] for s in results}),8)
        self.assertEqual(self.request('/api/samples',dict(site='x',profile='p',point='1',material='soil',latitude=91,longitude=0))[0],400)
        self.assertEqual(self.request('/api/samples',dict(site='x',profile='p',point='1',material='soil',latitude=45))[0],400)
    def test_qr_and_unknown(self):
        s=self.create();status,svg=self.request(f'/api/qr?id={s["id"]}&base=http%3A%2F%2F192.168.1.10%3A8000')
        self.assertEqual(status,200);self.assertIn(b'<svg',svg)
        self.assertEqual(self.request(f'/api/qr?id={s["id"]}&base=javascript:alert(1)')[0],400)
        self.assertEqual(self.request('/api/samples/999999')[0],404)
        self.assertEqual(self.request('/api/demo',{})[0],400)

if __name__=='__main__':unittest.main()
