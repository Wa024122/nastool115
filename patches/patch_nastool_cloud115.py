from pathlib import Path


ROOT = Path("/nas-tools")


def patch_once(path, old, new):
    file_path = ROOT / path
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch anchor not found in {file_path}: {old!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


patch_once(
    "app/utils/types.py",
    '    MINIO = "Minio移动"\n',
    '    MINIO = "Minio移动"\n    CLOUD115 = "115云端移动"\n',
)

patch_once(
    "app/conf/moduleconf.py",
    '        "miniocopy": RmtMode.MINIOCOPY\n',
    '        "miniocopy": RmtMode.MINIOCOPY,\n        "cloud115": RmtMode.CLOUD115\n',
)

patch_once(
    "app/conf/moduleconf.py",
    '        "softlink": RmtMode.SOFTLINK,\n        "move": RmtMode.MOVE\n',
    '        "softlink": RmtMode.SOFTLINK,\n        "move": RmtMode.MOVE,\n        "cloud115": RmtMode.CLOUD115\n',
)

patch_once(
    "app/downloader/downloader.py",
    "                        if self._pt_rmt_mode in [RmtMode.MOVE, RmtMode.RCLONE, RmtMode.MINIO]:\n",
    "                        if self._pt_rmt_mode in [RmtMode.MOVE, RmtMode.RCLONE, RmtMode.MINIO, RmtMode.CLOUD115]:\n",
)

patch_once(
    "app/filetransfer.py",
    "            elif rmt_mode == RmtMode.MINIOCOPY:\n"
    "                # Minio复制\n"
    "                retcode, retmsg = SystemUtils.minio_copy(file_item, target_file)\n",
    "            elif rmt_mode == RmtMode.MINIOCOPY:\n"
    "                # Minio复制\n"
    "                retcode, retmsg = SystemUtils.minio_copy(file_item, target_file)\n"
    "            elif rmt_mode == RmtMode.CLOUD115:\n"
    "                # 115云端移动\n"
    "                retcode, retmsg = SystemUtils.cloud115_move(file_item, target_file)\n",
)

patch_once(
    "app/filetransfer.py",
    "                    if not os.path.exists(ret_dir_path):\n"
    "                        log.debug(\"【Rmt】正在创建目录：%s\" % ret_dir_path)\n"
    "                        os.makedirs(ret_dir_path)\n",
    "                    if rmt_mode != RmtMode.CLOUD115 and not os.path.exists(ret_dir_path):\n"
    "                        log.debug(\"【Rmt】正在创建目录：%s\" % ret_dir_path)\n"
    "                        os.makedirs(ret_dir_path)\n",
)

patch_once(
    "app/filetransfer.py",
    "                        if rmt_mode != RmtMode.SOFTLINK:\n",
    "                        if rmt_mode not in [RmtMode.SOFTLINK, RmtMode.CLOUD115]:\n",
)

patch_once(
    "app/filetransfer.py",
    "        parser.add_argument('-m', '--mode', dest='mode', default='link',\n"
    "                            help='转移模式：link copy softlink move rclone rclonecopy minio miniocopy')\n",
    "        parser.add_argument('-m', '--mode', dest='mode', default='link',\n"
    "                            help='转移模式：link copy softlink move rclone rclonecopy minio miniocopy cloud115')\n",
)

patch_once(
    "app/utils/system_utils.py",
    "    def rclone_move(src, dest):\n",
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
    "    def rclone_move(src, dest):\n",
)

print("NASTool cloud115 transfer patch applied.")
