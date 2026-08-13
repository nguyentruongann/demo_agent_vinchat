import shutil

from src.backend.config import get_settings


def main() -> None:
    settings = get_settings()
    if settings.chroma_dir.exists():
        shutil.rmtree(settings.chroma_dir)
        print(f"Deleted: {settings.chroma_dir}")
    else:
        print(f"Nothing to delete: {settings.chroma_dir}")


if __name__ == "__main__":
    main()
