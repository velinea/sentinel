import json
import logging
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class RingBuffer:
    def __init__(self, max_seconds: int, fps: int):
        self.max_frames = max_seconds * fps
        self.frames: deque[bytes] = deque(
            maxlen=self.max_frames
        )
        self.timestamps: deque[float] = deque(
            maxlen=self.max_frames
        )

    def add(self, frame: bytes, timestamp: float):
        self.frames.append(frame)
        self.timestamps.append(timestamp)

    def snapshot(self):
        return list(self.frames), list(self.timestamps)

    def clear(self):
        self.frames.clear()
        self.timestamps.clear()


def probe_resolution(stream_url: str):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        stream_url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return (
                    stream["width"],
                    stream["height"],
                )
    except Exception:
        pass

    return None, None


RESTART_DELAY = 10


class CameraClipper:
    def __init__(
        self,
        name: str,
        stream_url: str,
        save_path: Path,
        buffer_seconds: int,
        max_seconds: int,
        fps: int,
        crf: int,
    ):
        self.name = name
        self.stream_url = stream_url
        self.save_path = save_path
        self.buffer = RingBuffer(buffer_seconds, fps)
        self.max_seconds = max_seconds
        self.fps = fps
        self.crf = crf

        self._reader_proc: subprocess.Popen | None = None
        self._writer_proc: subprocess.Popen | None = None

        self._recording = False
        self._lock = threading.Lock()
        self._start_event = threading.Event()
        self._shutdown = threading.Event()

        self._frame_width = 0
        self._frame_height = 0
        self._record_start = 0.0
        self._stretch = False
        self._output_width = 0
        self._stderr_tail = deque(maxlen=40)

    def start(self):
        self.save_path.mkdir(parents=True, exist_ok=True)

        w, h = probe_resolution(self.stream_url)
        if w and h:
            self._frame_width = w
            self._frame_height = h
            self._configure_stretch()
            logger.info(
                "%s: Detected %dx%d via %s",
                self.name, w, h, self.stream_url,
            )
        else:
            logger.warning(
                "%s: Could not detect resolution, "
                "using ffprobe fallback",
                self.name,
            )

        threading.Thread(
            target=self._reader_thread,
            name=f"clip-reader-{self.name}",
            daemon=True,
        ).start()

    def _launch_reader(self) -> bool:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-i", self.stream_url,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-r", str(self.fps),
            "pipe:1",
        ]

        try:
            self._reader_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error(
                "%s: ffmpeg not found", self.name
            )
            return False

        threading.Thread(
            target=self._drain_stderr,
            args=(self._reader_proc,),
            name=f"clip-stderr-{self.name}",
            daemon=True,
        ).start()

        return True

    def _configure_stretch(self):
        if self._frame_width == 0 or self._frame_height == 0:
            return

        ratio = self._frame_width / self._frame_height
        if abs(ratio - 4 / 3) < 0.15:
            self._stretch = True
            self._output_width = (
                (
                    self._frame_height * 16 // 9
                    + 1
                )
                // 2
                * 2
            )
            logger.info(
                "%s: 4:3 stream detected, "
                "stretching to %dx%d",
                self.name,
                self._output_width,
                self._frame_height,
            )

    def _drain_stderr(self, proc: subprocess.Popen | None):
        if proc is None or proc.stderr is None:
            return

        for line in proc.stderr:
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr_tail.append(text)
                logger.debug(
                    "%s: ffmpeg: %s", self.name, text
                )

    def _reader_thread(self):
        while not self._shutdown.is_set():
            if not self._launch_reader():
                self._shutdown.wait(RESTART_DELAY)
                continue

            logger.info(
                "%s: Clip reader started", self.name
            )
            self._run_reader_loop()

            if self._shutdown.is_set():
                break

            self._cleanup_reader()

            logger.warning(
                "%s: Clip reader died, "
                "restarting in %ds",
                self.name, RESTART_DELAY,
            )
            self._shutdown.wait(RESTART_DELAY)

        logger.info(
            "%s: Clip reader stopped", self.name
        )

    def _run_reader_loop(self):
        proc = self._reader_proc
        if proc is None or proc.stdout is None:
            return

        if self._frame_width == 0:
            self._wait_for_resolution(proc)

        if self._frame_width == 0:
            logger.error(
                "%s: Could not determine resolution",
                self.name,
            )
            return

        frame_size = (
            self._frame_width * self._frame_height * 3
        )

        while True:
            raw = proc.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break

            now = time.monotonic()
            self.buffer.add(raw, now)

            if self._start_event.is_set():
                self._start_event.clear()
                self._begin_recording(now)

            if self._recording:
                self._write_frame(raw)

                elapsed = now - self._record_start

                if elapsed >= self.max_seconds:
                    self._finish_recording()

        if self._recording:
            self._finish_recording()

    def _cleanup_reader(self):
        if self._reader_proc:
            self._reader_proc.terminate()
            try:
                self._reader_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._reader_proc.kill()
            self._reader_proc = None

        if self._recording:
            self._finish_recording()

    def _wait_for_resolution(self, proc):
        if self._frame_width > 0:
            return

        chunk = proc.stdout.read(256 * 1024)
        if not chunk:
            return

        w, h = self._fallback_parse_resolution(chunk)
        if w and h:
            self._frame_width = w
            self._frame_height = h
            self._configure_stretch()

            if self._frame_width > 0:
                frame_size = (
                    self._frame_width
                    * self._frame_height
                    * 3
                )
                offset = 0
                while offset + frame_size <= len(chunk):
                    frame = chunk[
                        offset : offset + frame_size
                    ]
                    self.buffer.add(
                        frame, time.monotonic()
                    )
                    offset += frame_size

    @staticmethod
    def _fallback_parse_resolution(header: bytes):
        for width in range(320, 3841, 16):
            for height in range(240, 2161, 16):
                pattern = f"{width}x{height}".encode()
                if pattern in header:
                    return width, height
        return None, None

    def notify_detection(self):
        with self._lock:
            if not self._recording:
                self._start_event.set()

    def _begin_recording(self, now: float):
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        clip_path = (
            self.save_path
            / f"{self.name}_{timestamp}.mp4"
        )

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s",
            f"{self._frame_width}x{self._frame_height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
        ]

        if self._stretch:
            cmd.extend([
                "-vf",
                f"scale={self._output_width}:"
                f"{self._frame_height}",
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(clip_path),
        ])

        try:
            self._writer_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error(
                "%s: ffmpeg not found", self.name
            )
            return

        self._stderr_tail.clear()
        threading.Thread(
            target=self._drain_stderr,
            args=(self._writer_proc,),
            name=f"clip-writer-stderr-{self.name}",
            daemon=True,
        ).start()

        self._recording = True
        self._record_start = now
        self._clip_path = clip_path

        frames, _timestamps = self.buffer.snapshot()
        for frame in frames:
            self._write_frame(frame)

        logger.info(
            "%s: Recording started (%s)",
            self.name,
            clip_path,
        )

    def _finish_recording(self):
        self._recording = False

        proc = self._writer_proc
        returncode = None
        if proc is not None:
            if proc.stdin:
                proc.stdin.close()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            returncode = proc.returncode

        self._writer_proc = None

        clip_path = getattr(self, "_clip_path", None)

        if clip_path and clip_path.exists():
            size = clip_path.stat().st_size
            if size > 0:
                size_mb = size / (1024 * 1024)
                logger.info(
                    "%s: Recording saved %s (%.1f MB)",
                    self.name,
                    clip_path,
                    size_mb,
                )
            else:
                logger.warning(
                    "%s: Recording produced an empty clip, "
                    "deleting %s",
                    self.name,
                    clip_path,
                )
                if returncode not in (None, 0):
                    logger.warning(
                        "%s: writer exited with %s: %s",
                        self.name,
                        returncode,
                        " | ".join(self._stderr_tail),
                    )
                try:
                    clip_path.unlink()
                except OSError:
                    pass
        else:
            logger.warning(
                "%s: Recording failed", self.name
            )

    def _write_frame(self, frame: bytes):
        if self._writer_proc and self._writer_proc.stdin:
            try:
                self._writer_proc.stdin.write(frame)
            except BrokenPipeError:
                self._finish_recording()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def shutdown(self):
        self._shutdown.set()
        self._cleanup_reader()


class ClipManager:
    def __init__(self, config):
        self.config = config
        self.clippers: dict[str, CameraClipper] = {}

        if not config.clips.enabled:
            return

        go2rtc_url = (
            config.go2rtc.url if config.go2rtc else None
        )
        save_path = Path(config.clips.save_path)

        for camera in config.cameras:
            if camera.source != "go2rtc":
                continue

            if not camera.go2rtc_src:
                continue

            clip_enabled = (
                camera.clip_enabled
                if camera.clip_enabled is not None
                else True
            )
            if not clip_enabled:
                continue

            cam_url = (
                camera.go2rtc_url or go2rtc_url
            )

            if not cam_url:
                logger.warning(
                    "%s: Clip enabled but no go2rtc "
                    "config",
                    camera.name,
                )
                continue

            max_seconds = (
                camera.clip_max_seconds
                if camera.clip_max_seconds is not None
                else config.clips.max_seconds
            )

            stream_url = (
                f"{cam_url}/api/stream.mp4"
                f"?src={camera.go2rtc_src}"
            )

            self.clippers[camera.name] = CameraClipper(
                name=camera.name,
                stream_url=stream_url,
                save_path=save_path / camera.name,
                buffer_seconds=config.clips.buffer_seconds,
                max_seconds=max_seconds,
                fps=config.clips.fps,
                crf=config.clips.crf,
            )

    def start(self):
        for name, clipper in self.clippers.items():
            clipper.start()

        self._cleanup_empty_clips()

    def _cleanup_empty_clips(self):
        root = Path(self.config.clips.save_path)
        if not root.is_dir():
            return

        removed = 0
        for clip in root.glob("**/*.mp4"):
            try:
                if clip.stat().st_size == 0:
                    clip.unlink()
                    removed += 1
            except OSError:
                continue

        if removed:
            logger.info(
                "Removed %d empty clip(s) from %s",
                removed, root,
            )

    def notify_detection(self, camera_name: str):
        clipper = self.clippers.get(camera_name)
        if clipper:
            clipper.notify_detection()

    def is_recording(self, camera_name: str) -> bool:
        clipper = self.clippers.get(camera_name)
        if clipper:
            return clipper.is_recording
        return False

    def shutdown(self):
        for clipper in self.clippers.values():
            clipper.shutdown()
