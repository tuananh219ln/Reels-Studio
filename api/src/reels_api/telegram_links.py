"""Shopee links sent to the bot in a private chat become the sender's products (docs/decisions/2026-11-28-telegram-links.md):
the same rows as the web's "Thêm sản phẩm", up to 50 links in one message, without calling Shopee here (the worker reads
each product's details later when a Shopee account has an App ID; the link's affiliate conversion is the Chrome
extension's job). The group is the one named on the message's first line, else the member's only one."""

import html
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import affiliate_rounds, shopee, telegram
from .models import KnowledgeTopic, User
from .ownership import can_add_products

MAX_LINKS = 50  # as the web's paste (routes_affiliate.MAX_LINKS)
URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def links_in(text: str) -> list[str]:
    """The Shopee addresses in a message, each once, in order."""
    found = (url.rstrip(".,;:!?)]}") for url in URL.findall(text))
    return list(dict.fromkeys(url for url in found if shopee.is_shopee_link(url)))


def _plain(text: str) -> str:
    stripped = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return " ".join("".join(c for c in stripped if not unicodedata.combining(c)).split())


def _topic(db: DbSession, user: User, text: str) -> tuple[KnowledgeTopic | None, str]:
    """The group to add to, or None and what to tell the member."""
    topics = [t for t in db.scalars(select(KnowledgeTopic).order_by(KnowledgeTopic.id)) if can_add_products(t, user.id)]
    if not topics:
        return None, "Bạn chưa có nhóm chủ đề nào để thêm sản phẩm. Tạo nhóm trên web trước, rồi gửi lại link."
    first = next((line for line in URL.sub("", text).splitlines() if line.strip()), "")
    wanted = _plain(first)
    if wanted:
        named = [t for t in topics if wanted in _plain(t.name) or _plain(t.name) in wanted]
        if len(named) == 1:
            return named[0], ""
    if len(topics) == 1:
        return topics[0], ""
    names = "\n".join(f"• {html.escape(t.name)}" for t in topics)
    return None, f"Bạn có nhiều nhóm. Gửi lại, ghi tên nhóm ở dòng đầu, rồi dán link bên dưới:\n{names}"


def handle(db: DbSession, message: dict, sender: int | None) -> bool:
    """Answers a private message that holds Shopee links; False when it holds none."""
    from .routes_affiliate import _from_links  # the web's own rule, so a Telegram product cannot differ

    text = message.get("text") or ""
    links = links_in(text)
    if not links:
        return False
    chat = message["chat"]["id"]
    user = db.scalar(select(User).where(User.telegram_chat_id == sender, User.is_active.is_(True)))
    if user is None:
        telegram.send_text(chat, telegram_commands_not_linked())
        return True
    topic, problem = _topic(db, user, text)
    if topic is None:
        telegram.send_text(chat, problem)
        return True
    cut = len(links) - MAX_LINKS
    added = skipped = 0
    for _, (_, new) in _from_links(
        db, topic, links[:MAX_LINKS], user.id, ask=affiliate_rounds.team_account(db, user.id) is not None
    ).items():
        added, skipped = added + new, skipped + (not new)
    db.commit()
    lines = [f"✅ Đã thêm {added} sản phẩm vào nhóm “{html.escape(topic.name)}”."]
    if skipped:
        lines.append(f"{skipped} link đã có sẵn nên bỏ qua.")
    if cut > 0:
        lines.append(f"Chỉ nhận {MAX_LINKS} link mỗi tin, còn {cut} link chưa thêm: gửi lại phần đó.")
    lines.append("Mở Affiliate › Sản phẩm để duyệt và chuyển link.")
    telegram.send_text(chat, "\n".join(lines))
    return True


def telegram_commands_not_linked() -> str:
    from .telegram_commands import NOT_LINKED

    return NOT_LINKED
