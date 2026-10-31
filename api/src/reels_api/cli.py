import argparse
import getpass
import sys
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from .config import ConfigError
from .db import get_engine
from .models import User
from .rules import RuleError, check_password, clean_email, clean_name
from .security import hash_password
from .sessions import revoke_sessions

Ask = Callable[[str], str]


class _VietnameseParser(argparse.ArgumentParser):
    def error(self, message: str):
        # argparse's own usage errors are English; keep every CLI error Vietnamese.
        print("Lỗi: lệnh không hợp lệ. Dùng: python -m reels_api create-user | worker", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None, ask: Ask = input, ask_secret: Ask = getpass.getpass) -> int:
    # Piped output on Windows defaults to the ANSI code page, which cannot encode Vietnamese.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    parser = _VietnameseParser(prog="reels_api", description="Công cụ quản trị Reels Studio.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "create-user",
        help="tạo người dùng; với email đã có thì đặt lại mật khẩu, kích hoạt lại và đăng xuất mọi phiên",
    )
    commands.add_parser("worker", help="chạy worker nhận job (viết kịch bản, render)")
    # Started by the worker for each job, in its own process group; not meant to be run by hand.
    run_job = commands.add_parser("run-job")
    run_job.add_argument("job_id", type=int)
    args = parser.parse_args(argv)

    if args.command == "worker":
        from .worker import main as worker_main
        return worker_main()
    if args.command == "run-job":
        from .worker import run_job_command
        return run_job_command(args.job_id)

    if sys.stdin is None or not sys.stdin.isatty():
        print("Lỗi: lệnh này cần chạy trong terminal để nhập mật khẩu ẩn", file=sys.stderr)
        return 2
    try:
        with sessionmaker(get_engine(), expire_on_commit=False)() as db:
            return create_or_reset_user(db, ask, ask_secret)
    except (EOFError, KeyboardInterrupt):
        print("\nĐã huỷ, không thay đổi gì.", file=sys.stderr)
        return 1
    except ConfigError as err:
        print(f"Lỗi: {err}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Lỗi: không kết nối được cơ sở dữ liệu. Postgres đã chạy chưa (docker compose up -d postgres)?",
              file=sys.stderr)
        return 1


def create_or_reset_user(db: DbSession, ask: Ask, ask_secret: Ask) -> int:
    email = _ask_valid(ask, "Email: ", clean_email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        name = _ask_valid(ask, "Tên: ", clean_name)
        password = _ask_password(ask_secret)
        db.add(User(email=email, name=name, password_hash=hash_password(password), is_active=True,
                    must_change_password=False))
        db.commit()
        print(f"Đã tạo người dùng {email}.")
        return 0

    answer = ask(f"Email {email} đã có. Đặt mật khẩu mới, kích hoạt lại và đăng xuất mọi phiên? (c/k): ")
    if answer.strip().lower() not in {"c", "co", "có", "y", "yes"}:
        print("Không thay đổi gì.", file=sys.stderr)
        return 1
    password = _ask_password(ask_secret)
    # The password typed here is the real one, so no forced change; the name is kept.
    user.password_hash = hash_password(password)
    user.is_active = True
    user.must_change_password = False
    revoke_sessions(db, user.id)
    db.commit()
    print(f"Đã đặt lại mật khẩu và kích hoạt lại {email}.")
    return 0


def _ask_valid(ask: Ask, prompt: str, clean: Callable[[str], str]) -> str:
    while True:
        try:
            return clean(ask(prompt))
        except RuleError as err:
            print(f"Lỗi: {err.message}", file=sys.stderr)


def _ask_password(ask_secret: Ask) -> str:
    while True:
        password = ask_secret("Mật khẩu (ẩn): ")
        try:
            check_password(password)
        except RuleError as err:
            print(f"Lỗi: {err.message}", file=sys.stderr)
            continue
        if ask_secret("Nhập lại mật khẩu: ") != password:
            print("Lỗi: hai lần nhập mật khẩu không khớp", file=sys.stderr)
            continue
        return password
