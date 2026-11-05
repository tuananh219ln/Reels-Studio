"""Per-scene effects, each a named preset (never a free slider): the transition into a scene and its colour.

The web preview copies these as CSS (web/src/components/video/preview/effects.ts); keep the two lists in step.

The colour presets' FFmpeg filter chains are adapted from AIEV (https://github.com/notivn/AIEVv2,
apps/server/src/color.ts), under its MIT licence:

    Copyright (c) 2026 noti.vn

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
    to permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions of
    the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
    THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
    CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
    IN THE SOFTWARE.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Transition:
    label: str
    xfade: str | None  # FFmpeg's xfade transition; None: a hard cut


@dataclass(frozen=True)
class ColorPreset:
    label: str
    filter: str  # an FFmpeg filter chain


# The transition into a scene from the one before it; a scene without one takes the video's (options.TRANSITIONS).
SCENE_TRANSITIONS: dict[str, Transition] = {
    "fade": Transition("Mờ dần", "fade"),
    "cut": Transition("Cắt thẳng", None),
    "slide": Transition("Trượt sang trái", "slideleft"),
    "slide_up": Transition("Trượt lên", "slideup"),
    "wipe": Transition("Quét ngang", "wipeleft"),
    "zoom": Transition("Phóng vào", "zoomin"),
    "circle": Transition("Mở vòng tròn", "circleopen"),
    "black": Transition("Qua màu đen", "fadeblack"),
    "flash": Transition("Chớp trắng", "fadewhite"),
    "dissolve": Transition("Hoà tan", "dissolve"),
    "blur": Transition("Nhoè ngang", "hblur"),
    "pixel": Transition("Vỡ điểm ảnh", "pixelize"),
}

COLOR_PRESETS: dict[str, ColorPreset] = {
    "natural": ColorPreset("Tự nhiên", "eq=contrast=1.06:saturation=1.12"),
    "bright": ColorPreset("Tươi sáng", "eq=brightness=0.03:contrast=1.08:saturation=1.22,vibrance=intensity=0.15"),
    "vivid": ColorPreset("Rực rỡ", "eq=contrast=1.12:saturation=1.3,vibrance=intensity=0.25"),
    "cinematic": ColorPreset(
        "Điện ảnh",
        "curves=master='0/0 0.25/0.22 0.75/0.78 1/1',"
        "colorbalance=rs=0.05:bs=-0.05:rm=0.03:bm=-0.02:rh=-0.02:bh=0.04,eq=saturation=1.05",
    ),
    "teal_orange": ColorPreset(
        "Xanh cam", "colorbalance=rs=0.12:bs=-0.10:rm=0.05:bm=-0.04:rh=-0.06:bh=0.10,eq=contrast=1.1:saturation=1.1"
    ),
    "vintage": ColorPreset(
        "Phim cũ",
        "curves=master='0/0.06 0.3/0.3 0.7/0.72 1/0.94',colorbalance=rh=0.05:bh=-0.06,eq=saturation=0.85:contrast=1.02",
    ),
    "matte": ColorPreset("Phim mờ", "curves=master='0/0.05 1/0.97',eq=contrast=1.05:saturation=0.9"),
    "golden": ColorPreset(
        "Nắng vàng",
        "colortemperature=temperature=4800,colorbalance=rm=0.06:bm=-0.04,eq=saturation=1.1:brightness=0.02",
    ),
    "warm": ColorPreset("Ấm", "colortemperature=temperature=5200,eq=saturation=1.08"),
    "cool": ColorPreset("Lạnh", "colortemperature=temperature=8200,eq=saturation=1.05"),
    "night": ColorPreset(
        "Đêm xanh",
        "colortemperature=temperature=9000,colorbalance=bs=0.08,eq=brightness=-0.03:contrast=1.1:saturation=0.95",
    ),
    "moody": ColorPreset("Trầm", "eq=brightness=-0.04:contrast=1.18:saturation=0.8,colorbalance=bs=0.05"),
    "pastel": ColorPreset("Pastel", "eq=brightness=0.05:contrast=0.92:saturation=0.85,colorbalance=rh=0.03:bh=0.03"),
    "mono": ColorPreset("Đen trắng", "hue=s=0,eq=contrast=1.15"),
}
