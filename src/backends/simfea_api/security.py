from pathlib import Path


def safe_upload_path(root: Path, filename: str) -> Path:
    name = Path(filename).name
    if not name:
        raise ValueError("Missing filename.")

    base = root.resolve()
    target = (base / name).resolve()
    if base != target.parent:
        raise ValueError("Invalid filename.")
    return target


def safe_child_dir(root: Path, child: str) -> Path:
    if not child or Path(child).name != child:
        raise ValueError("Invalid path segment.")

    base = root.resolve()
    target = (base / child).resolve()
    if base != target.parent:
        raise ValueError("Path is outside the allowed root.")
    return target
