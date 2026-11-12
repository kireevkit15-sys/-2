"""Offline launcher: only Python and the files in this folder are required."""
import argparse
import contextlib
import os
from pathlib import Path
import sys
import traceback
import webbrowser
from threading import Timer

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description='GeoTrace offline launcher')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        raise RuntimeError('Требуется Python 3.10 или новее. Установите его с python.org.')
    if not 1 <= args.port <= 65535:
        raise RuntimeError('Порт должен быть числом от 1 до 65535.')
    required = ['app.py', 'static/index.html', 'static/app.js', 'static/style.css', 'static/booklet.js', 'static/booklet.css',
                'vendor/qrcode-8.2-py3-none-any.whl',
                'vendor/colorama-0.4.6-py2.py3-none-any.whl']
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError('Неполная папка проекта. Распакуйте ВЕСЬ ZIP-архив через «Извлечь все», '
                           'затем запустите start.bat из распакованной папки. Не запускайте его внутри ZIP. '
                           'Отсутствуют: ' + ', '.join(missing))
    # Both wheels contain pure Python. Import directly from the local archives;
    # do not depend on pip, Internet, installed packages or an old virtualenv.
    sys.path[:0] = [str(ROOT / name) for name in required if name.endswith('.whl')]
    sys.path.insert(0, str(ROOT))
    import app
    app.init_db()
    try:
        server = app.ThreadingHTTPServer((args.host, args.port), app.Handler)
    except OSError as exc:
        raise RuntimeError(f'Не удалось открыть порт {args.port}. Закройте ранее запущенный сервер GeoTrace '
                           f'или выполните: python launcher.py --port {args.port + 1 if args.port < 65535 else 8000}. '
                           f'Системная ошибка: {exc}') from exc
    with server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'GeoTrace запущен: {url}', flush=True)
        print(f'База данных: {app.DB}', flush=True)
        print('Оставьте это окно открытым. Для остановки нажмите Ctrl+C.', flush=True)
        print(f'Телефон в той же Wi-Fi-сети: http://IPv4-адрес-компьютера:{server.server_port}', flush=True)
        print('IPv4 можно посмотреть командой ipconfig. Укажите адрес в настройке QR перед печатью.', flush=True)
        if not args.no_browser:
            def open_browser():
                try:
                    webbrowser.open(url)
                except Exception as exc:
                    print(f'Откройте {url} вручную. Браузер не запустился: {exc}', flush=True)
            timer = Timer(0.5, open_browser)
            timer.daemon = True
            timer.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nGeoTrace остановлен. Данные сохранены.', flush=True)
    return 0


class Tee:
    def __init__(self, *streams): self.streams = streams
    def write(self, value):
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)
    def flush(self):
        for stream in self.streams: stream.flush()


def run():
    try:
        log_dir = ROOT / 'data'
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / 'startup.log').open('a', encoding='utf-8') as log:
            with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
                print(f'\n--- GeoTrace startup | Python {sys.version.split()[0]} | {ROOT} ---', flush=True)
                try:
                    return main()
                except Exception:
                    traceback.print_exc()
                    print('Не удалось запустить GeoTrace. Подробности выше и в data/startup.log.', flush=True)
                    return 1
    except OSError as exc:
        print(f'Нет доступа к папке проекта: {exc}. Распакуйте архив в доступную для записи папку.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(run())
