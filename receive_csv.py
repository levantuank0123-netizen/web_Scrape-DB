"""Server tạm thời nhận CSV từ Chrome MCP về và lưu vào disk."""
import http.server
import socketserver
from pathlib import Path

OUT = Path(__file__).parent / "data" / "master_import.csv"
PORT = 8765


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(body, encoding="utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(f'{{"ok":true,"bytes":{len(body)}}}'.encode())
        print(f"[receive] Saved {len(body)} bytes to {OUT}")

    def log_message(self, *_a, **_kw):
        pass


print(f"Listening on 127.0.0.1:{PORT}, saving to {OUT}")
print("Will exit after receiving 1 POST.")
got_post = {"value": False}

orig_do_POST = Handler.do_POST
def do_POST_then_stop(self):
    orig_do_POST(self)
    got_post["value"] = True
Handler.do_POST = do_POST_then_stop

with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as srv:
    while not got_post["value"]:
        srv.handle_request()
print("Done.")
