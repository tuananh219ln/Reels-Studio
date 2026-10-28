from pathlib import Path


class RenderError(Exception):
    """Base for every expected render failure; the message is Vietnamese and user-facing."""


class InputError(RenderError):
    """The script, an image, the music file or a parameter is invalid."""


class ToolNotFoundError(RenderError):
    """ffmpeg or ffprobe is not installed."""


class FFmpegError(RenderError):
    def __init__(self, message: str, stderr_tail: str):
        super().__init__(f"{message}\n{stderr_tail}" if stderr_tail else message)
        self.stderr_tail = stderr_tail


class OutputNotReplacedError(RenderError):
    """Rendering succeeded but the output could not be moved into place; the video is kept elsewhere."""

    def __init__(self, message: str, kept_path: Path):
        super().__init__(message)
        self.kept_path = kept_path
