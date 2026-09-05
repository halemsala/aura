"""Lock de ficheiro por caminho — impede dois jobs a editar o mesmo ficheiro."""
import os
import time
import threading
from pathlib import Path

_mem = {}
_mem_lock = threading.Lock()


class FileBusy(RuntimeError):
    pass


class FileLock:
    def __init__(self, path, timeout: float = 8.0):
        self.path = Path(path)
        self.lock_path = Path(str(self.path) + ".alfredlock")
        self.timeout = float(timeout)
        self._fd = None
        self._key = str(self.path.resolve()) if self.path.exists() or self.path.parent.exists() else str(self.path)

    def acquire(self):
        deadline = time.time() + self.timeout
        while True:
            with _mem_lock:
                ev = _mem.get(self._key)
                if ev is None:
                    ev = threading.Event()
                    ev.set()
                    _mem[self._key] = ev
                if ev.is_set():
                    ev.clear()
                    owned = True
                else:
                    owned = False
            if owned:
                try:
                    self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                    self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    os.write(self._fd, str(os.getpid()).encode("ascii", "replace"))
                    return self
                except FileExistsError:
                    with _mem_lock:
                        _mem[self._key].set()
                    try:
                        age = time.time() - self.lock_path.stat().st_mtime
                        if age > 60:
                            try:
                                self.lock_path.unlink()
                            except OSError:
                                pass
                    except OSError:
                        pass
                except OSError:
                    with _mem_lock:
                        _mem[self._key].set()
                    raise
            if time.time() >= deadline:
                raise FileBusy(f"ficheiro ocupado por outro job: {self.path}")
            time.sleep(0.05)

    def release(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError:
            pass
        with _mem_lock:
            ev = _mem.get(self._key)
            if ev is not None:
                ev.set()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
