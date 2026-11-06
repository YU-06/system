import os
import secrets
from pathlib import Path

from dotenv import set_key


def initialize_environment(root: Path) -> Path:
    destination = root / ".env"
    template = (root / ".env.example").read_text(encoding="utf-8")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(template)
    for key in ("POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD"):
        set_key(str(destination), key, secrets.token_hex(32), quote_mode="never")
    destination.chmod(0o600)
    return destination


def main() -> None:
    try:
        initialize_environment(Path(__file__).resolve().parents[2])
    except FileExistsError as error:
        raise SystemExit("The local .env already exists and was not overwritten.") from error
    print("Created local .env with random development credentials. Values were not printed.")


if __name__ == "__main__":
    main()
