"""
Fırsat Radarı — Masaüstü Uygulaması
===================================
Kullanım:
  python main.py            -> Uygulama PENCERESİNİ açar (gerekirse tarama başlatır).
  python main.py --tray     -> Sessizce sistem tepsisine yerleşir; birkaç saatte bir
                               tarar ve yeni fırsatları / yaklaşan son tarihleri
                               Windows bildirimiyle haber verir.
  python main.py --scan     -> Tek seferlik tarama yapıp çıkar (test için).
  python main.py --serve    -> Sadece sunucu, http://127.0.0.1:8770 (tarayıcıdan test).

Her şey lokal (127.0.0.1). İnternete yalnızca halka açık etkinlik sayfalarını
OKUMAK için çıkar; hesap/şifre istemez, hiçbir kişisel veri göndermez.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

PORT = 8770
URL = f"http://127.0.0.1:{PORT}"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _start_server():
    from app.server import app
    httpd = make_server("127.0.0.1", PORT, app, server_class=_ThreadingWSGIServer)
    httpd.serve_forever()


def _already_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _ensure_server() -> bool:
    """Sunucuyu gerekirse başlatır. Bu süreç başlattıysa True döner."""
    if _already_running():
        return False
    threading.Thread(target=_start_server, daemon=True).start()
    for _ in range(25):
        if _already_running():
            break
        time.sleep(0.2)
    return True


def _notify(title, message):
    try:
        from app.tray import notify
        if notify(title, message):
            return
    except Exception:
        pass
    print(f"[bildirim] {title}: {message}")


def open_window():
    try:
        import webview
        webview.create_window("Fırsat Radarı", URL, width=1240, height=840,
                              min_size=(820, 600), background_color="#0d0c0a")
        webview.start()
    except Exception as e:
        print(f"[bilgi] pencere açılamadı ({e}); tarayıcıda açılıyor.")
        import webbrowser
        webbrowser.open(URL)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


def spawn_window():
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py")], cwd=BASE_DIR)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    os.chdir(BASE_DIR)
    args = sys.argv[1:]

    from app import engine

    if "--scan" in args:
        print(engine.run_scan(notify=lambda t, m: print(f"[bildirim] {t}: {m}")))
        return

    if "--serve" in args:                # yalnızca sunucu (tarayıcıdan test için)
        _start_server()
        return

    if "--tray" in args:
        _ensure_server()
        engine.start_scheduler(notify=_notify)
        from app.tray import run_tray
        run_tray(on_open=spawn_window, on_quit=lambda: os._exit(0))
        return

    started_here = _ensure_server()
    # Tepsi çalışmıyorsa ve son tarama eskiyse pencereyle birlikte tara.
    last = engine.last_run()
    stale = not last or datetime.fromisoformat(last) < datetime.now() - timedelta(hours=4)
    if started_here and stale:
        threading.Thread(target=engine.run_scan, daemon=True).start()
    open_window()


if __name__ == "__main__":
    main()
