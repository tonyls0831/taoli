import socketserver
import threading
from contextlib import contextmanager
from pathlib import Path


def file_snapshot(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


class RecordingProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.connection_count += 1
        self.request.recv(1024)
        self.request.sendall(b"HTTP/1.1 502 Offline Replay\r\nContent-Length: 0\r\n\r\n")


@contextmanager
def recording_proxy():
    with socketserver.TCPServer(("127.0.0.1", 0), RecordingProxyHandler) as server:
        server.connection_count = 0
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()
