"""Edit templates ("Mẫu dựng"): a video's look in rules that fit any video, so it can be put on another one.

"Gợi ý của app" (the studio's "Tự dựng") is the app's own template, here in code; the team saves its own from a video
it likes (table edit_templates). One template may be put on every new video (app setting DEFAULT_KEY), right after
its scenes are written. Every value is one of the render core's named presets.

A template holds:
- `transitions`: the transitions into the content scenes, in turn (the first scene takes the first, …, and they start
  over); empty leaves the scenes' own.
- `color`: every content scene's colour preset, or None to leave them.
- `scene_sounds` / `title_sounds`: sound effects added to every content scene / to the title scene, at their second.
- `end_layers`: text or sticker layers added to the last content scene (its call to action).
- `title_music`: the title scene's music level, or None to leave it.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session as DbSession

from reels_render.effects import COLOR_PRESETS, SCENE_TRANSITIONS
from reels_render.layers import ANIMATIONS, SIZES, STICKERS, TEXT_STYLES, Layer, render_layer
from reels_render.sounds import MUSIC_LEVELS, SOUND_VOLUMES, SOUNDS
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH

from .models import AppSetting, EditTemplate, Scene, SceneLayer, SceneSound, Video
from .videos import split_scenes

DEFAULT_KEY = "edit_template_default"
APP = "app"
APP_NAME = "Gợi ý của app"
MAX_ITEMS = 6


@dataclass
class Template:
    transitions: list[str] = field(default_factory=list)
    color: str | None = None
    scene_sounds: list[dict] = field(default_factory=list)
    title_sounds: list[dict] = field(default_factory=list)
    end_layers: list[dict] = field(default_factory=list)
    title_music: str | None = None

    def is_empty(self) -> bool:
        return not (
            self.transitions
            or self.color
            or self.scene_sounds
            or self.title_sounds
            or self.end_layers
            or self.title_music
        )


APP_TEMPLATE = Template(
    transitions=["zoom", "slide", "fade", "wipe"],
    scene_sounds=[{"sound": "whoosh", "start": 0.0, "volume": "soft"}],
    title_sounds=[{"sound": "rise", "start": 0.0, "volume": "soft"}],
    # Up near the top, clear of the scene's own text box and of the apps' bottom bar.
    end_layers=[
        {
            "kind": "text",
            "text": "Lưu video lại\n*để xem sau nhé!*",
            "sticker": "",
            "start": 0.5,
            "seconds": 3.0,
            "x": 540,
            "y": 420,
            "size": "medium",
            "style": "yellow",
            "animation": "slide_up",
        }
    ],
)


def _preset(value: object, presets: dict, label: str) -> str:
    if not isinstance(value, str) or value not in presets:
        raise ValueError(f"{label} không hợp lệ: {value!r}")
    return value


def _number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{label} phải từ {low:g} đến {high:g}")
    return float(value)


def _sounds(items: object) -> list[dict]:
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError(f"Âm thanh của mẫu phải là danh sách tối đa {MAX_ITEMS} âm")
    sounds = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Âm thanh của mẫu không hợp lệ")
        sounds.append(
            {
                "sound": _preset(item.get("sound"), SOUNDS, "Âm thanh"),
                "start": round(_number(item.get("start", 0), "Giây của âm", 0, 60), 2),
                "volume": _preset(item.get("volume", "normal"), SOUND_VOLUMES, "Mức âm"),
            }
        )
    return sounds


def _layers(items: object) -> list[dict]:
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError(f"Lớp của mẫu phải là danh sách tối đa {MAX_ITEMS} lớp")
    layers = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Lớp của mẫu không hợp lệ")
        kind = item.get("kind")
        if kind not in ("text", "sticker"):
            raise ValueError('Loại lớp phải là "text" hoặc "sticker"')
        layer = Layer(
            kind=kind,
            text=str(item.get("text") or "").strip() if kind == "text" else "",
            sticker=_preset(item.get("sticker"), STICKERS, "Sticker") if kind == "sticker" else "",
            start=round(_number(item.get("start", 0), "Giây của lớp", 0, 60), 2),
            seconds=round(_number(item.get("seconds", 2), "Số giây của lớp", 0.3, 60), 2),
            x=round(_number(item.get("x", FRAME_WIDTH // 2), "Vị trí", 0, FRAME_WIDTH)),
            y=round(_number(item.get("y", FRAME_HEIGHT // 2), "Vị trí", 0, FRAME_HEIGHT)),
            size=_preset(item.get("size", "medium"), SIZES, "Cỡ"),
            style=_preset(item.get("style", "outline"), TEXT_STYLES, "Kiểu chữ"),
            animation=_preset(item.get("animation", "fade"), ANIMATIONS, "Hiệu ứng vào"),
        )
        if kind == "text" and not layer.text:
            raise ValueError("Lớp chữ của mẫu đang trống")
        render_layer(layer)  # raises ValueError for text that does not fit
        layers.append(asdict(layer))
    return layers


def parse(data: object) -> Template:
    """A template from stored or sent JSON; anything outside the presets raises ValueError (in Vietnamese)."""
    if not isinstance(data, dict):
        raise ValueError("Mẫu dựng phải là một object")
    transitions = data.get("transitions") or []
    if not isinstance(transitions, list) or len(transitions) > MAX_ITEMS:
        raise ValueError(f"Chuyển cảnh của mẫu phải là danh sách tối đa {MAX_ITEMS} kiểu")
    color, music = data.get("color"), data.get("title_music")
    return Template(
        transitions=[_preset(name, SCENE_TRANSITIONS, "Chuyển cảnh") for name in transitions],
        color=None if color is None else _preset(color, COLOR_PRESETS, "Màu"),
        scene_sounds=_sounds(data.get("scene_sounds") or []),
        title_sounds=_sounds(data.get("title_sounds") or []),
        end_layers=_layers(data.get("end_layers") or []),
        title_music=None if music is None else _preset(music, MUSIC_LEVELS, "Mức nhạc"),
    )


def derive(title: Scene | None, scenes: list[Scene]) -> Template:
    """A video's look as a template: its scenes' transitions in order, its most used colour, the sounds of its first
    content scene that has any, its title's sounds and music level, and its last scene's layers."""
    colors = Counter(scene.color for scene in scenes if scene.color)
    with_sounds = next((scene for scene in scenes if scene.sounds), None)
    return Template(
        transitions=[scene.transition for scene in scenes if scene.transition][:MAX_ITEMS],
        color=colors.most_common(1)[0][0] if colors else None,
        scene_sounds=[_sound_fields(sound) for sound in (with_sounds.sounds if with_sounds else [])][:MAX_ITEMS],
        title_sounds=[_sound_fields(sound) for sound in (title.sounds if title else [])][:MAX_ITEMS],
        end_layers=[_layer_fields(layer) for layer in (scenes[-1].layers if scenes else [])][:MAX_ITEMS],
        title_music=title.music_level if title else None,
    )


def _sound_fields(sound: SceneSound) -> dict:
    return {"sound": sound.sound, "start": sound.start, "volume": sound.volume}


def _layer_fields(layer: SceneLayer) -> dict:
    fields = ("kind", "text", "sticker", "start", "seconds", "x", "y", "size", "style", "animation")
    return {name: getattr(layer, name) for name in fields}


def _add_sounds(db: DbSession, scene: Scene, sounds: list[dict]) -> None:
    have = {(sound.sound, sound.start) for sound in scene.sounds}
    for item in sounds:
        start = min(item["start"], max(0.0, scene.seconds - 0.1))
        if (item["sound"], start) not in have:
            db.add(SceneSound(scene_id=scene.id, sound=item["sound"], start=start, volume=item["volume"]))
            have.add((item["sound"], start))


def apply(db: DbSession, title: Scene | None, scenes: list[Scene], template: Template) -> None:
    """Puts the template on the video's scenes. Applying it again adds no sound or layer twice."""
    for index, scene in enumerate(scenes):
        if template.transitions:
            scene.transition = template.transitions[index % len(template.transitions)]
        if template.color:
            scene.color = template.color
        _add_sounds(db, scene, template.scene_sounds)
    if title is not None:
        _add_sounds(db, title, template.title_sounds)
        if template.title_music:
            title.music_level = template.title_music
    if scenes and template.end_layers:
        last = scenes[-1]
        have = {(layer.kind, layer.text, layer.sticker) for layer in last.layers}
        position = max((layer.position for layer in last.layers), default=0)
        for item in template.end_layers:
            if (item["kind"], item["text"], item["sticker"]) in have:
                continue
            position += 1
            start = min(item["start"], max(0.0, last.seconds - 0.3))
            db.add(SceneLayer(scene_id=last.id, position=position, **(item | {"start": start})))


def find(db: DbSession, key: object) -> tuple[str, Template] | None:
    """The template named by `key` ("app" or a team template's id), with its name; None when there is none."""
    if key == APP:
        return APP_NAME, APP_TEMPLATE
    if isinstance(key, int) and not isinstance(key, bool):
        row = db.get(EditTemplate, key)
        if row is not None:
            return row.name, parse(row.data)
    return None


def default_key(db: DbSession) -> object:
    setting = db.get(AppSetting, DEFAULT_KEY)
    return setting.value if setting is not None else None


def apply_default(db: DbSession, video: Video) -> None:
    """The team's template for new videos, if one is chosen, once the video's scenes exist."""
    found = find(db, default_key(db))
    if found is None:
        return
    db.flush()
    title, scenes = split_scenes(db, video)
    apply(db, title, scenes, found[1])


def summary(template: Template) -> list[str]:
    """What the template does, in Vietnamese, one line per part."""
    lines = []
    if template.transitions:
        lines.append("Chuyển cảnh: " + ", ".join(SCENE_TRANSITIONS[name].label for name in template.transitions))
    if template.color:
        lines.append(f"Màu: {COLOR_PRESETS[template.color].label}")
    for label, sounds in (("Âm mỗi cảnh", template.scene_sounds), ("Âm cảnh tiêu đề", template.title_sounds)):
        if sounds:
            lines.append(f"{label}: " + ", ".join(SOUNDS[item["sound"]].label for item in sounds))
    if template.title_music:
        lines.append(f"Cảnh tiêu đề: {MUSIC_LEVELS[template.title_music].label.lower()}")
    if template.end_layers:
        names = [
            item["text"].replace("*", "").replace("\n", " ")
            if item["kind"] == "text"
            else STICKERS[item["sticker"]].label
            for item in template.end_layers
        ]
        lines.append("Cảnh cuối: " + "; ".join(names))
    return lines
