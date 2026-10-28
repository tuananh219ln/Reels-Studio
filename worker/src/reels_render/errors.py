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


class StockSearchError(RenderError):
    """Stock image search could not run or failed (key, network, rate limit); the user is not asked."""


class MissingImagesError(RenderError):
    """Some scenes have no image and none was found, and there is nobody to ask for one."""

    def __init__(self, labels: list[str]):
        super().__init__(
            f"Chưa có ảnh cho: {', '.join(labels)}. Không tìm được ảnh phù hợp; "
            "thêm \"image\" hoặc \"keywords\" cụ thể hơn cho các cảnh này"
        )
        self.labels = labels
