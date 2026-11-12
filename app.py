"""Учебный реестр геохимических проб. Python 3.10+."""
import argparse
import csv
import io
import json
import math
import os
import re
import sqlite3
import tempfile
import zipfile
import shutil
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import qrcode
import qrcode.image.svg

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('GEOCHEM_DB', ROOT / 'data' / 'samples.sqlite3'))
STATUSES = ['Запланирована', 'Отобрана', 'Передана в лабораторию', 'В анализе', 'Результаты готовы']

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connection():
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con

def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connection() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, site TEXT NOT NULL,
          profile TEXT NOT NULL, point TEXT NOT NULL, material TEXT NOT NULL,
          latitude REAL, longitude REAL, collector TEXT NOT NULL, notes TEXT NOT NULL,
          status INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL REFERENCES samples(id),
          status INTEGER NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS results (
          id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL REFERENCES samples(id),
          element TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL,
          method TEXT NOT NULL, qualifier TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches (
          id INTEGER PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
          spec TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batch_samples (
          batch_id INTEGER NOT NULL REFERENCES batches(id),
          sample_id INTEGER UNIQUE NOT NULL REFERENCES samples(id),
          PRIMARY KEY(batch_id,sample_id));
        ''')

def text(data, key, required=False, limit=300):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ValueError(f'Некорректное поле: {key}')
    value = value.strip()
    if required and not value:
        raise ValueError(f'Заполните поле: {key}')
    return value

def coordinate(data, key, bound):
    value = data.get(key)
    if value is None or value == '':
        return None
    value = float(value)
    if not math.isfinite(value) or abs(value) > bound:
        raise ValueError('Координаты вне допустимого диапазона')
    return value

def create_sample(c, data):
    lat, lon = coordinate(data, 'latitude', 90), coordinate(data, 'longitude', 180)
    if (lat is None) != (lon is None):
        raise ValueError('Укажите обе координаты или оставьте обе пустыми')
    values = [text(data,k,k in ('site','profile','point','material'),2000 if k=='notes' else 300)
              for k in ('site','profile','point','material','collector','notes')]
    cur = c.execute('INSERT INTO samples(site,profile,point,material,collector,notes,latitude,longitude,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (*values,lat,lon,now()))
    sid = cur.lastrowid
    code = f'GC-{datetime.now(timezone.utc).year}-{sid:05d}'
    c.execute('UPDATE samples SET code=? WHERE id=?',(code,sid))
    c.execute('INSERT INTO events(sample_id,status,at) VALUES(?,?,?)',(sid,0,now()))
    return sid

def sample(c, sid):
    row = c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone()
    if row is None:
        raise LookupError('Проба не найдена')
    item = dict(row)
    item['events'] = [dict(r) for r in c.execute('SELECT status,at FROM events WHERE sample_id=? ORDER BY id',(sid,))]
    item['results'] = [dict(r) for r in c.execute('SELECT * FROM results WHERE sample_id=? ORDER BY id',(sid,))]
    return item

def integer(data, key, default, maximum):
    value = data.get(key, default)
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,9}', str(value)):
        raise ValueError(f'Ожидается целое число: {key}')
    value = int(value)
    if not 1 <= value <= maximum:
        raise ValueError(f'{key}: допустимо от 1 до {maximum}')
    return value


def batch_info(c, bid):
    row = c.execute('SELECT id,created_at,spec FROM batches WHERE id=?',(bid,)).fetchone()
    if row is None: raise LookupError('Серия не найдена')
    rows = c.execute('SELECT s.id,s.code FROM samples s JOIN batch_samples b ON b.sample_id=s.id WHERE b.batch_id=? ORDER BY s.id',(bid,)).fetchall()
    return dict(id=bid,created_at=row['created_at'],spec=json.loads(row['spec']),count=len(rows),
                first_code=rows[0]['code'],last_code=rows[-1]['code'])


def create_batch(c, data):
    key = text(data, 'request_key', True, 64)
    if not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', key):
        raise ValueError('Некорректный ключ запроса серии')
    profiles = integer(data,'profiles',1,10000)
    per_profile = integer(data,'per_profile',100,10000)
    start_profile = integer(data,'start_profile',1,1000000)
    start_point = integer(data,'start_point',1,1000000)
    if profiles * per_profile > 10000:
        raise ValueError('Не более 10 000 проб за одну серию')
    common = {k:text(data,k,k in ('site','material'),2000 if k=='notes' else 300)
              for k in ('site','material','collector','notes')}
    prefix = text(data,'profile_prefix',True,100)
    spec = dict(common,profiles=profiles,per_profile=per_profile,start_profile=start_profile,
                start_point=start_point,profile_prefix=prefix)
    encoded = json.dumps(spec,ensure_ascii=False,sort_keys=True)
    # Serialize writers, reserve all numbers, and commit the whole series together.
    c.execute('BEGIN IMMEDIATE')
    previous = c.execute('SELECT id,spec FROM batches WHERE request_key=?',(key,)).fetchone()
    if previous:
        if previous['spec'] != encoded:
            raise ValueError('Этот запрос уже использован. Откройте форму новой серии заново.')
        return batch_info(c,previous['id'])
    bid = c.execute('INSERT INTO batches(request_key,spec,created_at) VALUES(?,?,?)',(key,encoded,now())).lastrowid
    for profile in range(start_profile,start_profile+profiles):
        for point in range(start_point,start_point+per_profile):
            sid = create_sample(c,dict(common,profile=f'{prefix}{profile:02d}',point=f'Т-{point:03d}'))
            c.execute('INSERT INTO batch_samples(batch_id,sample_id) VALUES(?,?)',(bid,sid))
    return batch_info(c,bid)


def qr_bytes(base, sid):
    u = urlsplit(base)
    if u.scheme not in ('http','https') or not u.netloc or u.username or u.password or u.query or u.fragment or len(base)>300:
        raise ValueError('Укажите HTTP(S)-адрес приложения без параметров')
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=8,border=4)
    qr.add_data(f'{base.rstrip("/")}/?sample={sid}');qr.make(fit=True)
    out = io.BytesIO();qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(out)
    return out.getvalue()


class Handler(BaseHTTPRequestHandler):
    def send(self, body, status=200, kind='application/json; charset=utf-8', headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body,ensure_ascii=False).encode() if kind.startswith('application/json') else body.encode()
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            with connection() as c:
                if path == '/api/samples':
                    return self.send([dict(r) for r in c.execute('SELECT s.*,b.batch_id FROM samples s LEFT JOIN batch_samples b ON b.sample_id=s.id ORDER BY s.id DESC')])
                if path == '/api/batches':
                    return self.send([batch_info(c,r['id']) for r in c.execute('SELECT id FROM batches ORDER BY id DESC')])
                archive = re.fullmatch(r'/api/batches/(\d+)/qr.zip',path)
                if archive:
                    bid = int(archive[1]); batch_info(c,bid)
                    base = parse_qs(urlsplit(self.path).query).get('base',[''])[0].rstrip('/')
                    rows = c.execute('SELECT s.* FROM samples s JOIN batch_samples b ON b.sample_id=s.id WHERE b.batch_id=? ORDER BY s.id',(bid,)).fetchall()
                    # Validate before beginning a download; spool large archives to disk.
                    qr_bytes(base,rows[0]['id'])
                    with tempfile.SpooledTemporaryFile(max_size=8*1024*1024) as out:
                        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive_file:
                            manifest = io.StringIO();manifest.write('\ufeff')
                            writer = csv.writer(manifest,delimiter=';')
                            writer.writerow(['Number','Profile','Point','URL'])
                            for row in rows:
                                archive_file.writestr(row['code']+'.svg',qr_bytes(base,row['id']))
                                writer.writerow(["'"+v if v.startswith(('=','+','-','@','\t','\r')) else v for v in [row['code'],row['profile'],row['point'],f'{base}/?sample={row["id"]}']])
                            archive_file.writestr('registry.csv',manifest.getvalue())
                        size=out.tell();out.seek(0)
                        self.send_response(200)
                        self.send_header('Content-Type','application/zip')
                        self.send_header('Content-Disposition',f'attachment; filename="GeoTrace-batch-{bid}.zip"')
                        self.send_header('Content-Length',str(size))
                        self.send_header('Cache-Control','no-store');self.end_headers()
                        shutil.copyfileobj(out,self.wfile)
                    return
                if re.fullmatch(r'/api/samples/\d+',path):
                    return self.send(sample(c,int(path.rsplit('/',1)[1])))
                if path == '/api/export':
                    out = io.StringIO(); out.write('\ufeff')
                    writer = csv.writer(out, delimiter=';')
                    writer.writerow(['Номер','Участок','Профиль','Точка','Материал','Широта WGS84','Долгота WGS84','Исполнитель','Статус','Описание','Элемент','Значение','Единицы','Метод','Квалификатор'])
                    for row in c.execute('SELECT * FROM samples ORDER BY id'):
                        s = sample(c,row['id'])
                        for r in s['results'] or [{}]:
                            vals = [s['code'],s['site'],s['profile'],s['point'],s['material'],s['latitude'],s['longitude'],s['collector'],STATUSES[s['status']],s['notes'],r.get('element',''),r.get('value',''),r.get('unit',''),r.get('method',''),r.get('qualifier','')]
                            writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in vals])
                    return self.send(out.getvalue(),kind='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="samples.csv"'})
                if path == '/api/qr':
                    query = parse_qs(urlsplit(self.path).query)
                    sid = int(query.get('id',['0'])[0]); sample(c,sid)
                    base = query.get('base',[''])[0].rstrip('/')
                    return self.send(qr_bytes(base,sid),kind='image/svg+xml')
            files = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path in files:
                mime = {'/':'text/html','/app.js':'application/javascript','/style.css':'text/css'}[path]
                return self.send((ROOT/'static'/files[path]).read_bytes(),kind=mime+'; charset=utf-8')
            raise LookupError('Страница не найдена')
        except LookupError as e: self.send({'error':str(e)},404)
        except (ValueError,TypeError) as e: self.send({'error':str(e)},400)

    def do_POST(self):
        try:
            # Same-origin JSON writes; no cross-origin permission is granted.
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                return self.send({'error':'Запрос с другого сайта запрещён'},403)
            size = int(self.headers.get('Content-Length','0'))
            if size < 1 or size > 20000: raise ValueError('Некорректный размер запроса')
            if self.headers.get_content_type() != 'application/json': raise ValueError('Ожидается JSON')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('Ожидается объект')
            path = urlsplit(self.path).path
            with connection() as c:
                if path == '/api/batches':
                    result = create_batch(c,data)
                    c.commit()
                    return self.send(result,201)
                if path == '/api/samples':
                    sid = create_sample(c,data)
                    return self.send(sample(c,sid),201)
                if path == '/api/demo':
                    if c.execute('SELECT count(*) FROM samples').fetchone()[0]:
                        raise ValueError('Учебный набор можно добавить только в пустую базу')
                    for i in range(1,9):
                        sid = create_sample(c,dict(site='Учебный участок «Северный»',profile=f'ПР-{1+(i-1)//4:02}',point=f'Т-{i:03}',material='Почва, горизонт B',collector='Учебная группа',notes='Вымышленные данные для демонстрации. Координаты условные.',latitude=60.10+i*.001,longitude=59.30+i*.002))
                        stage = (i-1)%5
                        for st in range(1,stage+1): c.execute('INSERT INTO events(sample_id,status,at) VALUES(?,?,?)',(sid,st,now()))
                        c.execute('UPDATE samples SET status=? WHERE id=?',(stage,sid))
                        if stage==4:
                            c.execute('INSERT INTO results(sample_id,element,value,unit,method,qualifier,at) VALUES(?,?,?,?,?,?,?)',(sid,'Cu',42.5,'мг/кг','ICP-MS','=','2026-11-10T10:00:00+00:00'))
                    return self.send({'ok':True},201)
                m = re.fullmatch(r'/api/samples/(\d+)/(status|results)',path)
                if not m: raise LookupError('Маршрут не найден')
                sid = int(m[1]); s = sample(c,sid)
                if m[2]=='status':
                    status = data.get('status')
                    if type(status) is not int or status != s['status']+1 or status >= len(STATUSES):
                        raise ValueError('Можно перейти только к следующему этапу')
                    if status==4 and not s['results']: raise ValueError('Сначала внесите результат анализа')
                    c.execute('UPDATE samples SET status=? WHERE id=?',(status,sid))
                    c.execute('INSERT INTO events(sample_id,status,at) VALUES(?,?,?)',(sid,status,now()))
                else:
                    if s['status']!=3: raise ValueError('Результаты вносятся на этапе «В анализе»')
                    value = float(data.get('value',''))
                    if not math.isfinite(value) or value<0: raise ValueError('Концентрация должна быть конечным неотрицательным числом')
                    qualifier = data.get('qualifier','=')
                    if qualifier not in ('=','<'): raise ValueError('Некорректный квалификатор')
                    c.execute('INSERT INTO results(sample_id,element,value,unit,method,qualifier,at) VALUES(?,?,?,?,?,?,?)',(sid,text(data,'element',True,30),value,text(data,'unit',True,30),text(data,'method',True,100),qualifier,now()))
                return self.send(sample(c,sid))
        except LookupError as e: self.send({'error':str(e)},404)
        except (ValueError,TypeError,OverflowError) as e: self.send({'error':str(e)},400)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',default=8000,type=int)
    args=parser.parse_args();init_db()
    print(f'GeoTrace: http://{args.host}:{args.port} | SQLite: {DB}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
