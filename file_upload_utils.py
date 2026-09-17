"""
file_upload_utils.py
---------------------
Shared, security-conscious helpers for handling user-uploaded files
(profile pictures, and later CSV/Excel datasets). Centralizing this logic
avoids re-implementing validation in every route.
"""
import os
import uuid
from werkzeug.utils import secure_filename

# --- Profile picture upload settings ---
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_SIZE_BYTES = 3 * 1024 * 1024  # 3 MB

# --- Dataset upload settings ---
ALLOWED_DATASET_EXTENSIONS = {"csv", "xlsx", "xls"}
MAX_DATASET_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB

PROFILE_PICS_SUBDIR = os.path.join("uploads", "profile_pics")
DATASETS_SUBDIR = os.path.join("uploads", "datasets")


def _extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_allowed_image(filename):
    return bool(filename) and _extension(filename) in ALLOWED_IMAGE_EXTENSIONS


def is_allowed_dataset(filename):
    return bool(filename) and _extension(filename) in ALLOWED_DATASET_EXTENSIONS


def file_size_ok(file_storage, max_bytes):
    """Check size without loading the whole file into memory twice.
    Werkzeug's FileStorage wraps a stream we can seek."""
    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size <= max_bytes, size


def safe_unique_filename(original_filename, employee_code=None, prefix=None):
    """Builds a filename that:
      - is passed through werkzeug's secure_filename (strips path separators,
        '..', and other dangerous characters — this is our path-traversal
        defense)
      - has a random UUID component so filenames never collide and cannot be
        guessed/enumerated by an attacker
    """
    ext = _extension(original_filename)
    safe_base = secure_filename(original_filename.rsplit(".", 1)[0]) or "file"
    unique = uuid.uuid4().hex[:12]
    parts = [p for p in [prefix, employee_code, safe_base[:30], unique] if p]
    return secure_filename("_".join(parts)) + f".{ext}"


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def resolve_upload_path(static_folder, subdir, filename):
    """Resolves the absolute path for a file inside our managed upload
    directories, and defends against path traversal by re-checking that the
    resolved path is still inside the intended directory (defense in depth
    on top of secure_filename)."""
    base_dir = os.path.abspath(os.path.join(static_folder, subdir))
    ensure_dir(base_dir)
    candidate = os.path.abspath(os.path.join(base_dir, filename))
    if not candidate.startswith(base_dir + os.sep) and candidate != base_dir:
        raise ValueError("Invalid file path (path traversal attempt blocked).")
    return candidate


def delete_file_if_exists(static_folder, relative_path):
    if not relative_path:
        return
    full_path = os.path.join(static_folder, relative_path)
    full_path = os.path.abspath(full_path)
    static_abs = os.path.abspath(static_folder)
    # Only ever delete files that are actually inside our static folder.
    if full_path.startswith(static_abs) and os.path.isfile(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass
