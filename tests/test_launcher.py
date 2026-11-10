"""Real subprocess startup, without site-packages, pip or requirements.txt."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='GeoTrace ')
        self.root = Path(self.tmp.name) / 'Геохимия с пробелами'
        self.root.mkdir()
        for name in ('app.py', 'launcher.py'):
            shutil.copy2(ROOT/name, self.root/name)
        for name in ('static', 'vendor'):
            shutil.copytree(ROOT/name, self.root/name)
        # A correctly packaged launcher must not need requirements.txt at all.
        self.assertFalse((self.root/'requirements.txt').exists())
        self.env = dict(os.environ, GEOCHEM_DB=str(self.root/'data'/'test.sqlite3'), PYTHONUTF8='1')
    def tearDown(self): self.tmp.cleanup()
    def command(self, port):
        return [sys.executable, '-S', str(self.root/'launcher.py'), '--no-browser', '--host', '127.0.0.1', '--port', str(port)]
    def test_launch_from_different_directory_and_persist(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        for run in range(2):
            proc=subprocess.Popen(self.command(port),cwd=self.tmp.name,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if proc.poll() is not None: self.fail(proc.stdout.read().decode('utf-8'))
                    try:
                        with urllib.request.urlopen(url+'/api/samples',timeout=.3) as res: rows=json.load(res)
                        break
                    except OSError: time.sleep(.05)
                else: self.fail('Server did not become ready')
                if run==0:
                    req=urllib.request.Request(url+'/api/samples',json.dumps(dict(site='Тест',profile='ПР-01',point='001',material='Почва')).encode(),{'Content-Type':'application/json'})
                    with urllib.request.urlopen(req) as res: sample=json.load(res)
                    with urllib.request.urlopen(url+f'/api/qr?id={sample["id"]}&base=http://127.0.0.1:{port}') as res:
                        self.assertIn(b'<svg',res.read())
                else:
                    self.assertEqual(len(rows),1);self.assertEqual(rows[0]['site'],'Тест')
            finally:
                proc.terminate();proc.communicate(timeout=5)
        self.assertIn('GeoTrace запущен',(self.root/'data'/'startup.log').read_text(encoding='utf-8'))
    def test_missing_files_have_actionable_error(self):
        (self.root/'vendor'/'qrcode-8.2-py3-none-any.whl').unlink()
        res=subprocess.run(self.command(8000),env=self.env,cwd=self.tmp.name,capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(res.returncode,1)
        self.assertIn('Неполная папка проекта',res.stdout+res.stderr)
        self.assertIn('qrcode-8.2', (self.root/'data'/'startup.log').read_text(encoding='utf-8'))
    def test_busy_port_has_actionable_error(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));s.listen()
            res=subprocess.run(self.command(s.getsockname()[1]),env=self.env,cwd=self.tmp.name,capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(res.returncode,1)
        self.assertIn('Не удалось открыть порт',res.stdout+res.stderr)
    def test_invalid_port(self):
        res=subprocess.run(self.command(70000),env=self.env,capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(res.returncode,1)
        self.assertIn('Порт должен быть',res.stdout+res.stderr)

if __name__=='__main__': unittest.main()
