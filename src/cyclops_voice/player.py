from __future__ import annotations
import queue
import threading
from typing import Iterator, Protocol
import numpy as np


class AudioSink(Protocol):
    def write(self, block: np.ndarray) -> None: ...
    def close(self) -> None: ...


class SoundDeviceSink:
    def __init__(self, sample_rate: int, device: str | int | None = None):
        import sounddevice as sd
        self._stream = sd.OutputStream(
            samplerate=sample_rate, channels=2, dtype="float32",
            device=device or None,
        )
        self._stream.start()

    def write(self, block: np.ndarray) -> None:
        self._stream.write(block)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class Player:
    """Streams PCM buffers for one job at a time with pause/stop/skip control."""
    BLOCK = 1024  # frames per sink write

    def __init__(self, sample_rate: int, sink: AudioSink):
        self.sample_rate = sample_rate
        self._sink = sink
        self._jobs: "queue.Queue[tuple[str, Iterator[np.ndarray]]]" = queue.Queue()
        self._state = "idle"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._skip = threading.Event()
        self._pause = threading.Event()
        self._idle = threading.Event(); self._idle.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _set(self, s: str) -> None:
        with self._lock:
            self._state = s

    def submit(self, job_id: str, buffers: Iterator[np.ndarray]) -> None:
        self._idle.clear()
        self._jobs.put((job_id, buffers))

    def stop(self) -> None:
        self._stop.set()
        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def skip(self) -> None:
        self._skip.set()

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def _run(self) -> None:
        while True:
            try:
                job_id, buffers = self._jobs.get(timeout=0.1)
            except queue.Empty:
                if self._jobs.empty():
                    self._set("idle"); self._idle.set()
                continue
            self._stop.clear(); self._skip.clear()
            self._set("speaking")
            self._play_job(buffers)
            if self._jobs.empty():
                self._set("idle"); self._idle.set()

    def _play_job(self, buffers: Iterator[np.ndarray]) -> None:
        for buf in buffers:
            if self._stop.is_set() or self._skip.is_set():
                break
            buf = np.asarray(buf, dtype=np.float32)
            for i in range(0, len(buf), self.BLOCK):
                if self._stop.is_set() or self._skip.is_set():
                    return
                while self._pause.is_set() and not self._stop.is_set():
                    self._set("paused")
                    threading.Event().wait(0.05)
                self._set("speaking")
                self._sink.write(buf[i:i + self.BLOCK])
