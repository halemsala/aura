from __future__ import annotations
import socket
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.framing import send_msg, recv_msg

class FramingTests(unittest.TestCase):
    def test_roundtrip_large(self):
        srv, cli = socket.socketpair()
        big = {"data": "x" * 50_000, "n": 42}
        def server():
            msg = recv_msg(srv)
            send_msg(srv, {"echo": msg["n"], "len": len(msg["data"])})
            srv.close()
        t = threading.Thread(target=server)
        t.start()
        send_msg(cli, big)
        resp = recv_msg(cli)
        cli.close()
        t.join()
        self.assertEqual(resp["echo"], 42)
        self.assertEqual(resp["len"], 50_000)

if __name__ == "__main__":
    unittest.main()
