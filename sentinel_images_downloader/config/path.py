import pathlib

# Assumes: config/path.py → inside sentinel_images_downloader/config/
PROJECT_DIR = pathlib.Path(__file__).resolve().parents[2]

LOGS_DIR = PROJECT_DIR / "logs"

directories_to_create = [
    LOGS_DIR,
]

def ensure_dirs_exist(paths: list[pathlib.Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

ensure_dirs_exist(paths=directories_to_create)