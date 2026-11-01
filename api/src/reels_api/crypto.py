"""Secrets kept in the database (Fanpage tokens, LLM, stock-library and AI-image API keys), encrypted with one key in the storage folder.

The api and the worker share that folder and the key is not in the database, so a database dump alone does not
reveal a secret. Losing the key only means pasting the secrets again.
"""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import config

KEY_FILE = ".settings-key"


class CannotDecrypt(Exception):
    """The storage folder's key is not the one the secret was encrypted with."""


def _fernet() -> Fernet:
    path = config.storage_dir() / KEY_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".settings-key-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(Fernet.generate_key())
            # A link never replaces a key made a moment earlier by the other process.
            try:
                os.link(temp, path)
            except FileExistsError:
                pass
        finally:
            Path(temp).unlink(missing_ok=True)
    return Fernet(path.read_bytes().strip())


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        raise CannotDecrypt from None
