import concurrent.futures
import csv
import io
import json
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch
import test_app
app=test_app.app

class BulkTest(unittest.TestCase):
    setUpClass=classmethod(test_app.WorkflowTest.setUpClass.__func__)
    tearDownClass=classmethod(test_app.WorkflowTest.tearDownClass.__func__)
    request=test_app.WorkflowTest.request
    def data(self, **kwargs):
        return dict(site='Большой участок',material='Почва',profile_prefix='ПР-',profiles=2,per_profile=3,
                    start_profile=5,start_point=10,request_key=uuid.uuid4().hex,**kwargs)
    def test_create_10000_and_retry(self):
        d=self.data();d.update(profiles=100,per_profile=100)
        status,b=self.request('/api/batches',d);self.assertEqual(status,201);self.assertEqual(b['count'],10000)
        status,retry=self.request('/api/batches',d);self.assertEqual(status,201);self.assertEqual(b,retry)
        rows=[s for s in self.request('/api/samples')[1] if s['batch_id']==b['id']]
        self.assertEqual(len({r['code'] for r in rows}),10000)
        self.assertEqual(len({(r['profile'],r['point']) for r in rows}),10000)
        self.assertTrue(all(r['status']==0 and r['latitude'] is None for r in rows))
        d['per_profile']=99
        self.assertEqual(self.request('/api/batches',d)[0],400)
    def test_concurrent_retry_and_zip(self):
        d=self.data()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.request('/api/batches',d),range(2)))
        self.assertEqual(results[0],results[1]);b=results[0][1]
        status,raw=self.request(f'/api/batches/{b["id"]}/qr.zip?base=http://192.168.1.10:8000')
        self.assertEqual(status,200)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIsNone(z.testzip());svgs=[n for n in z.namelist() if n.endswith('.svg')];self.assertEqual(len(svgs),6)
            rows=list(csv.reader(io.StringIO(z.read('registry.csv').decode('utf-8-sig')),delimiter=';'))
            self.assertEqual(len(rows),7)
            for r in rows[1:]:
                self.assertTrue(r[3].startswith('http://192.168.1.10:8000/?sample='))
                sid=r[3].split('=')[-1];s=self.request('/api/samples/'+sid)[1]
                self.assertEqual(r[0],s['code']);self.assertIn(b'<svg',z.read(s['code']+'.svg'))
    def test_validation_and_rollback(self):
        for changes in [dict(profiles=101,per_profile=100),dict(profiles=0),dict(per_profile=1.2),dict(start_point=-1),dict(site='')]:
            d=self.data();d.update(changes);self.assertEqual(self.request('/api/batches',d)[0],400)
        d=self.data();original=app.create_sample;calls=0
        def fail(c,data):
            nonlocal calls
            calls+=1
            if calls==3:raise ValueError('simulated failure')
            return original(c,data)
        before=len(self.request('/api/samples')[1])
        with patch.object(app,'create_sample',side_effect=fail):self.assertEqual(self.request('/api/batches',d)[0],400)
        self.assertEqual(len(self.request('/api/samples')[1]),before)
        with app.connection() as c:self.assertIsNone(c.execute('SELECT id FROM batches WHERE request_key=?',(d['request_key'],)).fetchone())
    def test_coordinates_order_and_retry(self):
        d=self.data();d['coordinates_text']='60.1; 59.1\n60,2\t59,2\n0 0\n-90; -180\n90; 180\n-12.5 45.5'
        status,b=self.request('/api/batches',d);self.assertEqual(status,201)
        rows=sorted([r for r in self.request('/api/samples')[1] if r['batch_id']==b['id']],key=lambda r:r['id'])
        self.assertEqual([(r['latitude'],r['longitude']) for r in rows],[(60.1,59.1),(60.2,59.2),(0,0),(-90,-180),(90,180),(-12.5,45.5)])
        self.assertEqual([(r['profile'],r['point']) for r in rows],[('ПР-05','Т-010'),('ПР-05','Т-011'),('ПР-05','Т-012'),('ПР-06','Т-010'),('ПР-06','Т-011'),('ПР-06','Т-012')])
        self.assertEqual(self.request('/api/batches',d)[1],b)
        d['coordinates_text']=d['coordinates_text'].replace('60.1','60.3')
        self.assertEqual(self.request('/api/batches',d)[0],400)
        app.init_db()
        persisted=self.request('/api/samples/'+str(rows[0]['id']))[1]
        self.assertEqual(persisted['latitude'],60.1)
        self.assertIn('60.1',self.request('/api/export')[1].decode('utf-8-sig'))
    def test_invalid_coordinates_create_nothing(self):
        before=len(self.request('/api/samples')[1])
        for raw in ['60;59', '60;59\n'*5+'91;59', '60;59\n'*5+'NaN;20', '60;59\n'*5+'60;181', '60;59\n'*5+'60', ['60','59'], '60;59\n'*2+'\n'+'60;59\n'*3]:
            d=self.data();d['coordinates_text']=raw
            self.assertEqual(self.request('/api/batches',d)[0],400)
        self.assertEqual(len(self.request('/api/samples')[1]),before)
    def test_coordinates_large_payload(self):
        d=self.data();d.update(profiles=100,per_profile=100,coordinates_text='60.123456; 59.234567\n'*10000)
        status,b=self.request('/api/batches',d);self.assertEqual(status,201);self.assertEqual(b['count'],10000)
        with app.connection() as c:
            row=c.execute('SELECT count(*) n FROM samples s JOIN batch_samples b ON b.sample_id=s.id WHERE b.batch_id=? AND s.latitude=? AND s.longitude=?',(b['id'],60.123456,59.234567)).fetchone()
            self.assertEqual(row['n'],10000)

    def test_legacy_db_migration(self):
        saved=app.DB
        with tempfile.TemporaryDirectory() as tmp:
            try:
                app.DB=Path(tmp)/'old.sqlite3'
                # Simulate a database from the previous release with real sample history.
                app.init_db()
                with app.connection() as c:
                    sid=app.create_sample(c,dict(site='Существующая проба',profile='1',point='1',material='Почва'))
                    c.execute('DROP TABLE batch_samples');c.execute('DROP TABLE batches')
                app.init_db();app.init_db()
                with app.connection() as c:self.assertEqual(app.sample(c,sid)['site'],'Существующая проба')
            finally:app.DB=saved

if __name__=='__main__':unittest.main()
