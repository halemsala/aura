from __future__ import annotations
import asyncio
import logging
import threading
import time
from typing import List, Optional

try:
    import zmq
    import msgpack
    ZMQ_OK = True
except ImportError:
    ZMQ_OK = False

logger = logging.getLogger("zmq_router")
FRONTEND_PORTS = [5555, 5556, 5558]
BACKEND_PORT = 5560

class XPUBXSUBRouter:
    def __init__(self, frontend_ports: Optional[List[int]] = None, backend_port: int = BACKEND_PORT) -> None:
        self.frontend_ports = frontend_ports or FRONTEND_PORTS
        self.backend_port = backend_port
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not ZMQ_OK:
            logger.error("zmq/msgpack unavailable")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="xpub-xsub-router", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            ctx = None
            try:
                ctx = zmq.Context.instance()
                xsub = ctx.socket(zmq.XSUB)
                xsub.setsockopt(zmq.LINGER, 0)
                xsub.setsockopt(zmq.RCVHWM, 10000)
                for p in self.frontend_ports:
                    try:
                        xsub.connect(f"tcp://127.0.0.1:{p}")
                        logger.info("XSUB connected %s", p)
                    except zmq.ZMQError as e:
                        logger.warning("XSUB connect %s failed: %s", p, e)
                xpub = ctx.socket(zmq.XPUB)
                xpub.setsockopt(zmq.LINGER, 0)
                xpub.setsockopt(zmq.SNDHWM, 10000)
                xpub.bind(f"tcp://127.0.0.1:{self.backend_port}")
                poller = zmq.Poller()
                poller.register(xsub, zmq.POLLIN)
                poller.register(xpub, zmq.POLLIN)
                while not self._stop.is_set():
                    events = dict(poller.poll(500))
                    if xsub in events:
                        raw = xsub.recv(zmq.NOBLOCK)
                        try:
                            # binary-safe: try msgpack unpack/repack; fallback passthrough
                            try:
                                obj = msgpack.unpackb(raw, raw=False, strict_map_key=False)
                                out = msgpack.packb(obj, use_bin_type=True)
                            except Exception:
                                out = raw
                            xpub.send(out)
                        except zmq.ZMQError:
                            pass
                    if xpub in events:
                        # subscription messages forward to publishers
                        try:
                            sub_msg = xpub.recv(zmq.NOBLOCK)
                            xsub.send(sub_msg)
                        except zmq.ZMQError:
                            pass
            except Exception as e:
                logger.error("router crash, reconnect in 2s: %s", e)
                time.sleep(2.0)
            finally:
                try:
                    if ctx is not None:
                        pass
                except Exception:
                    pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = XPUBXSUBRouter()
    r.start()
    time.sleep(3600)
