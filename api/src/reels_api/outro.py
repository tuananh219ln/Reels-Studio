"""The "Cảnh kết Theo dõi & Chia sẻ": a topic group's switch (`knowledge_topics.outro_cta`) ends each of its new videos
on one shared follow-and-share scene, which takes the place of a closing call to action of the script.

The scene is a "Cảnh động" (motion.py) with fixed markup, narration and a "Ting" at 1.9 s. Its clip is the same for
every video, so HyperFrames renders it once: the first outro scene gets an ordinary motion job (queued by the worker's
round, `fill`), the clip is kept at `cache_key()`, and every later outro scene copies it without a render. Changing
the markup or the timings changes the key, so a new look renders again.
"""

import hashlib
import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import knowledge
from .clips import check_clip
from .models import ACTIVE_JOB_STATUSES, Job, Scene, SceneSound, Video
from .script_rules import CROSSFADE_SIDE_SECONDS
from .storage import DirectoryStorage
from .uploads import UploadRejected
from .videos import active_job, new_key, split_scenes

log = logging.getLogger(__name__)

SECONDS = 4.5
VOICE = "Theo dõi và chia sẻ để cả nhà cùng biết thêm điều bổ ích nhé!"
SOUND, SOUND_START, SOUND_VOLUME = "ding", 1.9, "normal"
# Added to the script prompt of a group with the switch on, so the AI writes no call to action of its own.
SCRIPT_FORMAT = (
    "CẢNH KẾT: không viết cảnh kêu gọi theo dõi, chia sẻ, thả tim, lưu lại hay bình luận ở cuối kịch bản; "
    "app tự thêm cảnh kết “Theo dõi & Chia sẻ” sau cảnh nội dung cuối cùng."
)
# A last content scene whose words ask for this is the script's call to action, which the outro replaces.
CALL_TO_ACTION = re.compile(
    r"theo dõi|follow|chia sẻ|share|đăng ký|subscribe|thả tim|bấm like|nhấn like|lưu lại|bình luận|comment",
    re.IGNORECASE,
)

HTML = """<style>
  #root{font-family:"Be Vietnam Pro",sans-serif;background:linear-gradient(160deg,#FFF7ED 0%,#FFE0C2 100%);overflow:hidden}
  .abs{position:absolute;left:0;width:1080px;text-align:center}
  .blob{position:absolute;border-radius:50%}
  .t1{top:430px;font-size:64px;font-weight:600;color:#1F2937;letter-spacing:1px}
  .t2{top:520px;font-size:104px;font-weight:800;color:#FF5A36;line-height:1.1}
  .t3{top:650px;font-size:104px;font-weight:800;color:#1F2937;line-height:1.1}
  .btnwrap{position:absolute;left:190px;top:900px;width:700px;height:190px}
  .btn{position:absolute;left:0;top:0;width:700px;height:190px;border-radius:95px;display:flex;align-items:center;justify-content:center;gap:28px;font-size:68px;font-weight:800;box-shadow:0 14px 0 rgba(31,41,55,.18)}
  .b1{background:#FF4D4F;color:#fff}
  .b2{background:#14B8A6;color:#fff}
  .ripple{position:absolute;left:0;top:0;width:700px;height:190px;border-radius:95px;border:6px solid #14B8A6;opacity:0}
  .bell{position:absolute;left:800px;top:790px;width:150px;height:150px;transform-origin:75px 10px;filter:drop-shadow(0 6px 0 rgba(31,41,55,.15))}
  .wave{position:absolute;left:830px;top:800px;width:90px;height:90px;border-radius:50%;border:6px solid #FFB400;opacity:0}
  .share{top:1250px;display:flex;justify-content:center;align-items:center;gap:30px;font-size:62px;font-weight:700;color:#1F2937}
  .sub{top:1370px;font-size:50px;font-weight:500;color:#4B5563}
</style>
<div class="blob" style="left:-220px;top:-160px;width:620px;height:620px;background:rgba(20,184,166,.14)"></div>
<div class="blob" style="left:760px;top:1400px;width:560px;height:560px;background:rgba(255,180,0,.2)"></div>
<div class="abs t1">Thấy hữu ích?</div>
<div class="abs t2">THEO DÕI</div>
<div class="abs t3">&amp; CHIA SẺ</div>
<div class="btnwrap">
  <div class="btn b1" id="b1">
    <svg width="76" height="76" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round"><path d="M12 4v16M4 12h16"/></svg>
    THEO DÕI
  </div>
  <div class="btn b2" id="b2">
    <svg width="76" height="76" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>
    ĐÃ THEO DÕI
  </div>
  <div class="ripple"></div>
</div>
<div class="wave w1"></div><div class="wave w2"></div>
<svg class="bell" viewBox="0 0 24 24"><path d="M12 2.5a1.6 1.6 0 0 1 1.6 1.6v.5c2.6.7 4.4 3 4.4 5.8v3.7l1.7 2.6c.4.6 0 1.3-.7 1.3H5c-.7 0-1.1-.7-.7-1.3L6 14.1V10.4c0-2.8 1.8-5.1 4.4-5.8v-.5A1.6 1.6 0 0 1 12 2.5z" fill="#FFB400"/><path d="M9.8 19.2a2.3 2.3 0 0 0 4.4 0z" fill="#FFB400"/><circle cx="18.2" cy="5" r="3.2" fill="#FF4D4F"/></svg>
<div class="abs share" id="share">
  <svg width="84" height="84" viewBox="0 0 24 24" fill="none" stroke="#14B8A6" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 13v6a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6"/><path d="M12 15V3M7.5 7.5L12 3l4.5 4.5"/></svg>
  Chia sẻ cho người thân
</div>
<div class="abs sub" id="sub">để cả nhà cùng biết thêm điều bổ ích</div>
<script>
gsap.set("#b2",{opacity:0});
tl.from(".t1",{y:40,opacity:0,duration:.5,ease:"power3.out"},0.05);
tl.from(".t2",{y:60,opacity:0,duration:.55,ease:"back.out(1.6)"},0.25);
tl.from(".t3",{y:60,opacity:0,duration:.55,ease:"back.out(1.6)"},0.45);
tl.from(".btnwrap",{scale:0,opacity:0,duration:.55,ease:"back.out(2)",transformOrigin:"50% 50%"},0.95);
tl.from(".bell",{y:-120,opacity:0,duration:.5,ease:"bounce.out"},1.3);
tl.to(".bell",{rotation:22,duration:.12,ease:"sine.inOut"},1.8)
  .to(".bell",{rotation:-20,duration:.18,ease:"sine.inOut"})
  .to(".bell",{rotation:14,duration:.16,ease:"sine.inOut"})
  .to(".bell",{rotation:-10,duration:.16,ease:"sine.inOut"})
  .to(".bell",{rotation:0,duration:.2,ease:"sine.out"});
tl.fromTo(".w1",{opacity:.9,scale:.6},{opacity:0,scale:2.2,duration:.7,ease:"power2.out",immediateRender:false},1.9);
tl.fromTo(".w2",{opacity:.9,scale:.6},{opacity:0,scale:2.2,duration:.7,ease:"power2.out",immediateRender:false},2.1);
tl.to(".btnwrap",{scale:.93,duration:.1,ease:"power2.in",transformOrigin:"50% 50%"},1.9);
tl.to("#b1",{opacity:0,duration:.15},1.95);
tl.to("#b2",{opacity:1,duration:.15},1.95);
tl.to(".btnwrap",{scale:1,duration:.35,ease:"back.out(3)"},2.0);
tl.fromTo(".ripple",{opacity:1,scale:1},{opacity:0,scale:1.25,duration:.6,ease:"power2.out",immediateRender:false},2.0);
tl.from("#share",{y:70,opacity:0,duration:.5,ease:"power3.out"},2.5);
tl.from("#sub",{y:40,opacity:0,duration:.5,ease:"power3.out"},2.8);
tl.to("#share svg",{y:-14,duration:.3,yoyo:true,repeat:3,ease:"sine.inOut"},3.0);
</script>"""


def cache_key() -> str:
    """Where the rendered clip is kept for every video: named by the markup and the length the motion job renders
    (motion.run), so a changed look or crossfade never reuses an old clip."""
    from .motion import SPARE_SECONDS

    length = round(SECONDS + 2 * CROSSFADE_SIDE_SECONDS + SPARE_SECONDS, 2)
    digest = hashlib.sha256(f"{HTML}\n{length}".encode()).hexdigest()[:16]
    return f"outro/follow-share-{digest}.mp4"


def is_outro(scene: Scene) -> bool:
    return bool(scene.motion and scene.motion.get("outro"))


def is_call_to_action(scene: Scene) -> bool:
    return bool(CALL_TO_ACTION.search(f"{scene.text or ''}\n{scene.voice_text or ''}"))


def wanted(db: DbSession, video: Video) -> bool:
    group = knowledge.topic_of(db, video)
    return bool(group and group.outro_cta)


def add(db: DbSession, storage: DirectoryStorage, video: Video) -> Scene | None:
    """Ends a newly written video on the outro when its group has the switch on: a last content scene that asks to
    follow, share or comment goes (the outro says it), and the outro scene comes last, with the cached clip when there
    is one. Nothing when the switch is off or the video already has it. The caller commits."""
    if not wanted(db, video):
        return None
    db.flush()
    _, scenes = split_scenes(db, video)
    if any(is_outro(scene) for scene in scenes):
        return None
    if len(scenes) > 1 and is_call_to_action(scenes[-1]):
        db.delete(scenes.pop())
    scene = Scene(
        video_id=video.id,
        is_title=False,
        position=(scenes[-1].position if scenes else 0) + 1,
        text="",
        voice_text=VOICE,
        seconds=SECONDS,
        seconds_auto=False,
        keywords=[],
        keywords_en=[],
        image_prompt="",
        motion={"html": HTML, "seconds": SECONDS, "photo_key": None, "clip_key": None, "pending": False, "outro": True},
    )
    db.add(scene)
    db.flush()
    db.add(SceneSound(scene_id=scene.id, sound=SOUND, start=SOUND_START, volume=SOUND_VOLUME))
    _copy_cached(storage, video, scene)
    return scene


def _copy_cached(storage: DirectoryStorage, video: Video, scene: Scene) -> bool:
    """The cached clip becomes the scene's clip, as a motion job's would (motion.attach); False when none is kept."""
    cached = cache_key()
    if not storage.exists(cached):
        return False
    try:
        clip = check_clip(storage.path(cached))
    except UploadRejected:
        log.warning("The cached outro clip %s is unusable; it renders again", cached)
        storage.delete(cached)
        return False
    key = new_key(video.id, f"motion-{scene.id}", clip.extension)
    storage.save_file(key, storage.path(cached))
    scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = key, round(clip.seconds, 3), 0, 1
    scene.video_loop, scene.video_sound, scene.words = False, False, None
    scene.seconds, scene.seconds_auto = SECONDS, False
    scene.motion = {**scene.motion, "clip_key": key, "pending": False}
    return True


def keep(storage: DirectoryStorage, scene: Scene, target) -> None:
    """Called by motion.attach: the first outro clip rendered is kept for every later video."""
    if is_outro(scene) and scene.motion.get("html") == HTML and not storage.exists(cache_key()):
        storage.save_file(cache_key(), target)
        log.info("Kept the outro clip as %s", cache_key())


def fill(db: DbSession, storage: DirectoryStorage) -> None:
    """The worker's round: each outro scene still without its clip gets the cached one, or, while none is kept yet,
    one motion job renders it (only one at a time, so the clip is rendered once). A scene whose outro render failed is
    left to a member ("Thử lại" on its job). The caller commits."""
    waiting = [
        scene
        for scene in db.scalars(
            select(Scene)
            .where(Scene.motion["outro"].as_boolean().is_(True), Scene.video_key.is_(None), Scene.image_key.is_(None))
            .order_by(Scene.id)
            .limit(50)
        ).all()
        if not scene.motion.get("clip_key") and not scene.motion.get("pending")
    ]
    if not waiting:
        return
    rendering = db.scalar(
        select(Job.id)
        .join(Scene, Scene.id == Job.scene_id)
        .where(Job.kind == "motion", Job.status.in_(ACTIVE_JOB_STATUSES), Scene.motion["outro"].as_boolean().is_(True))
        .limit(1)
    )
    for scene in waiting:
        video = db.scalar(select(Video).where(Video.id == scene.video_id).with_for_update())
        if video is None or active_job(db, video.id) is not None:
            continue  # the next round tries again
        if _copy_cached(storage, video, scene):
            log.info("Scene %s: the cached outro clip", scene.id)
            continue
        if rendering is not None:
            return  # the one render under way fills the cache; the others copy it then
        failed = db.scalar(
            select(Job.id).where(Job.scene_id == scene.id, Job.kind == "motion", Job.status == "failed").limit(1)
        )
        if failed is not None:
            continue
        try:
            with db.begin_nested():
                scene.motion = {**scene.motion, "pending": True}
                db.add(
                    Job(
                        video_id=video.id,
                        kind="motion",
                        status="queued",
                        created_by_id=video.created_by_id,
                        scene_id=scene.id,
                    )
                )
                db.flush()
        except IntegrityError:
            continue
        log.info("Queued the outro render on scene %s of video %s", scene.id, video.id)
        return
