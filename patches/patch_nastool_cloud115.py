import re
from pathlib import Path


ROOT = Path("/nas-tools")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def patch_regex(path, pattern, replacement, flags=0):
    text = read(path)
    if "CLOUD115" in text and "cloud115" in text:
        return
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"Patch pattern not found in {ROOT / path}: {pattern}")
    write(path, new_text)


def patch_text(path, old, new):
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch anchor not found in {ROOT / path}: {old!r}")
    write(path, text.replace(old, new, 1))


def ensure_rmt_mode():
    path = "app/utils/types.py"
    text = read(path)
    if "CLOUD115" in text:
        return
    new_text, count = re.subn(
        r'(^\s+MINIO\s*=\s*["\'].+?["\']\s*$)',
        r'\1\n    CLOUD115 = "115云端移动"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError("Could not add RmtMode.CLOUD115 in app/utils/types.py")
    write(path, new_text)


def ensure_moduleconf():
    path = "app/conf/moduleconf.py"
    text = read(path)
    if '"cloud115"' in text:
        return

    text, count = re.subn(
        r'("miniocopy"\s*:\s*RmtMode\.MINIOCOPY)(,?)',
        r'\1,\n        "cloud115": RmtMode.CLOUD115',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not add cloud115 to primary RMT_MODES")

    move_anchor = '"move": RmtMode.MOVE'
    index = text.rfind(move_anchor)
    if index != -1:
        insert_at = index + len(move_anchor)
        text = text[:insert_at] + ',\n        "cloud115": RmtMode.CLOUD115' + text[insert_at:]
    write(path, text)


def ensure_downloader_move_mode():
    patch_text(
        "app/downloader/downloader.py",
        "if self._pt_rmt_mode in [RmtMode.MOVE, RmtMode.RCLONE, RmtMode.MINIO]:",
        "if self._pt_rmt_mode in [RmtMode.MOVE, RmtMode.RCLONE, RmtMode.MINIO, RmtMode.CLOUD115]:",
    )


def ensure_filetransfer():
    path = "app/filetransfer.py"
    text = read(path)
    if "SystemUtils.cloud115_move" not in text:
        old = "                retcode, retmsg = SystemUtils.minio_copy(file_item, target_file)\n"
        new = (
            old
            + "            elif rmt_mode == RmtMode.CLOUD115:\n"
            + "                # 115 cloud move\n"
            + "                retcode, retmsg = SystemUtils.cloud115_move(file_item, target_file)\n"
        )
        if old not in text:
            raise RuntimeError("Could not find minio_copy transfer anchor in app/filetransfer.py")
        text = text.replace(old, new, 1)

    text = text.replace(
        "if rmt_mode != RmtMode.SOFTLINK:",
        "if rmt_mode not in [RmtMode.SOFTLINK, RmtMode.CLOUD115]:",
        1,
    )

    text = text.replace(
        "help='转移模式：link copy softlink move rclone rclonecopy minio miniocopy'",
        "help='转移模式：link copy softlink move rclone rclonecopy minio miniocopy cloud115'",
        1,
    )

    write(path, text)


def ensure_system_utils():
    path = "app/utils/system_utils.py"
    text = read(path)
    if "def cloud115_move" in text:
        return
    old = "    def rclone_move(src, dest):\n"
    new = (
        "    def cloud115_move(src, dest):\n"
        "        \"\"\"\n"
        "        Move and rename a file directly inside 115 cloud storage.\n"
        "        \"\"\"\n"
        "        try:\n"
        "            from app.utils.cloud115_utils import Cloud115Mover\n"
        "            return Cloud115Mover().move(src, dest)\n"
        "        except Exception as err:\n"
        "            ExceptionUtils.exception_traceback(err)\n"
        "            return -1, str(err)\n\n"
        "    @staticmethod\n"
        + old
    )
    if old not in text:
        raise RuntimeError("Could not find rclone_move anchor in app/utils/system_utils.py")
    write(path, text.replace(old, new, 1))


ensure_rmt_mode()
ensure_moduleconf()
ensure_downloader_move_mode()
ensure_filetransfer()
ensure_system_utils()

print("NASTool cloud115 transfer patch applied.")
