from pathlib import Path


MAIN = Path("/nas-tools/web/main.py")
NAVBAR = Path("/nas-tools/web/static/components/layout/navbar/index.js")


ROUTE = r'''

CLOUD115_CONFIG_FILE = "/config/cloud115.json"
CLOUD115_SCHEDULER_STARTED = False
CLOUD115_RUNNING = False


def cloud115_default_config():
    return {
        "cookie": "",
        "source_path": "/nastool",
        "target_path": "/nastool-transfer",
        "delay_seconds": 2,
        "jitter_seconds": 1,
        "cooldown_seconds": 90,
        "retry_times": 4,
        "check_for_relogin": True,
        "auto_enabled": False,
        "interval_minutes": 60,
        "delete_extras": True,
        "last_run": "",
        "last_message": "",
        "last_status": None,
    }


def cloud115_load_config():
    import json
    import os

    cfg = cloud115_default_config()
    if os.path.exists(CLOUD115_CONFIG_FILE):
        try:
            with open(CLOUD115_CONFIG_FILE, "r", encoding="utf-8") as fp:
                saved = json.load(fp)
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def cloud115_save_config(cfg):
    import json
    import os

    os.makedirs(os.path.dirname(CLOUD115_CONFIG_FILE), exist_ok=True)
    with open(CLOUD115_CONFIG_FILE, "w", encoding="utf-8") as fp:
        json.dump(cfg, fp, ensure_ascii=False, indent=2)


def cloud115_normalize_cookie(cookie):
    return " ".join((cookie or "").replace("\r", "\n").split())


def cloud115_cookie_fingerprint(cookie):
    import hashlib

    cookie = cloud115_normalize_cookie(cookie)
    if not cookie:
        return ""
    digest = hashlib.sha256(cookie.encode("utf-8")).hexdigest()
    return f"{digest[:8]}...{digest[-8:]}"


def cloud115_get_media_exts():
    try:
        from app.conf import RMT_MEDIAEXT
        return {str(ext).lower() for ext in RMT_MEDIAEXT}
    except Exception:
        return {
            ".mp4", ".mkv", ".ts", ".iso", ".rmvb", ".avi", ".mov", ".mpeg", ".mpg",
            ".wmv", ".3gp", ".asf", ".m4v", ".flv", ".m2ts", ".strm", ".tp", ".f4v",
        }


def cloud115_call_worker(python, worker, args, env):
    import json as jsonlib
    import subprocess

    proc = subprocess.run(
        [python, worker] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    body = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or body or "115 worker failed").strip())
    data = jsonlib.loads(body or "{}")
    if not data.get("ok"):
        raise RuntimeError(data.get("message") or "115 worker failed")
    return data.get("message")


def cloud115_delete_extra_files(other_files, python, worker, env):
    count = 0
    for item in other_files:
        path = item.get("path")
        if not path:
            continue
        cloud115_call_worker(python, worker, ["delete", path], env)
        count += 1
    return count


def cloud115_execute(cfg):
    import json as jsonlib
    import os
    import posixpath
    import shutil
    import subprocess
    import tempfile
    from app.filetransfer import FileTransfer
    from app.utils.types import RmtMode, SyncType

    source_path = (cfg.get("source_path") or "").strip()
    target_path = (cfg.get("target_path") or "").strip()
    cookie = (cfg.get("cookie") or "").strip()
    if not source_path:
        raise RuntimeError("Source path is required")
    if not target_path:
        raise RuntimeError("Target path is required")
    if not cookie:
        raise RuntimeError("115 Cookie is required")

    cookie = cloud115_normalize_cookie(cookie)
    os.environ["CLOUD115_COOKIES"] = cookie
    os.environ.pop("CLOUD115_COOKIE_FILE", None)
    os.environ["CLOUD115_DELAY_SECONDS"] = str(cfg.get("delay_seconds") or 0)
    os.environ["CLOUD115_JITTER_SECONDS"] = str(cfg.get("jitter_seconds") or 0)
    os.environ["CLOUD115_COOLDOWN_SECONDS"] = str(cfg.get("cooldown_seconds") or 0)
    os.environ["CLOUD115_RETRY_TIMES"] = str(cfg.get("retry_times") or 1)
    os.environ["CLOUD115_CHECK_FOR_RELOGIN"] = "true" if cfg.get("check_for_relogin", True) else "false"
    os.environ["CLOUD115_COOKIE_STORE"] = "/config/cloud115.cookie"

    env = os.environ.copy()
    env["CLOUD115_COOKIES"] = cookie
    env.pop("CLOUD115_COOKIE_FILE", None)
    env["CLOUD115_DELAY_SECONDS"] = str(cfg.get("delay_seconds") or 0)
    env["CLOUD115_JITTER_SECONDS"] = str(cfg.get("jitter_seconds") or 0)
    env["CLOUD115_COOLDOWN_SECONDS"] = str(cfg.get("cooldown_seconds") or 0)
    env["CLOUD115_RETRY_TIMES"] = str(cfg.get("retry_times") or 1)
    env["CLOUD115_CHECK_FOR_RELOGIN"] = "true" if cfg.get("check_for_relogin", True) else "false"
    env["CLOUD115_COOKIE_STORE"] = "/config/cloud115.cookie"
    python = env.get("CLOUD115_PYTHON", "/opt/python312/bin/python3.12")
    worker = env.get("CLOUD115_WORKER", "/nas-tools/app/utils/cloud115_worker.py")
    proc = subprocess.run(
        [python, worker, "walk", source_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Failed to read 115 source path").strip())
    walked = jsonlib.loads((proc.stdout or "{}").strip())
    if not walked.get("ok"):
        raise RuntimeError(walked.get("message") or "Failed to read 115 source path")

    files = walked.get("files") or []
    media_exts = cloud115_get_media_exts()
    subtitle_exts = {".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".sup"}
    media_files = [
        item for item in files
        if os.path.splitext(item.get("name") or item.get("path") or "")[-1].lower() in media_exts
    ]
    subtitle_files = [
        item for item in files
        if os.path.splitext(item.get("name") or item.get("path") or "")[-1].lower() in subtitle_exts
    ]
    other_files = [
        item for item in files
        if item not in media_files and item not in subtitle_files
    ]
    if not media_files:
        raise RuntimeError("No media files found in source path")

    tmp_root = tempfile.mkdtemp(prefix="cloud115-virtual-")
    virtual_src = os.path.join(tmp_root, "src")
    virtual_dst = os.path.join(tmp_root, "dst")
    os.makedirs(virtual_src, exist_ok=True)
    os.makedirs(virtual_dst, exist_ok=True)
    local_files = []
    remote_source = source_path.rstrip("/") or "/"
    for item in media_files + subtitle_files:
        remote_file = item.get("path") or ""
        rel = posixpath.relpath(remote_file, remote_source).replace("/", os.sep)
        local_file = os.path.join(virtual_src, rel)
        os.makedirs(os.path.dirname(local_file), exist_ok=True)
        with open(local_file, "wb") as fp:
            fp.write(b"0")
        if item in media_files:
            local_files.append(local_file)

    old_env = {
        "CLOUD115_SRC_PREFIX": os.environ.get("CLOUD115_SRC_PREFIX"),
        "CLOUD115_REMOTE_SRC_ROOT": os.environ.get("CLOUD115_REMOTE_SRC_ROOT"),
        "CLOUD115_DEST_PREFIX": os.environ.get("CLOUD115_DEST_PREFIX"),
        "CLOUD115_REMOTE_DEST_ROOT": os.environ.get("CLOUD115_REMOTE_DEST_ROOT"),
    }
    os.environ["CLOUD115_SRC_PREFIX"] = virtual_src
    os.environ["CLOUD115_REMOTE_SRC_ROOT"] = remote_source
    os.environ["CLOUD115_DEST_PREFIX"] = virtual_dst
    os.environ["CLOUD115_REMOTE_DEST_ROOT"] = target_path.rstrip("/") or "/"
    try:
        ret, ret_msg = FileTransfer().transfer_media(
            in_from=SyncType.MAN,
            in_path=virtual_src,
            files=local_files,
            target_dir=virtual_dst,
            rmt_mode=RmtMode.CLOUD115,
            min_filesize=0,
            root_path=True,
        )
        cleanup_count = 0
        if ret and cfg.get("delete_extras", True):
            cleanup_count = cloud115_delete_extra_files(other_files, python, worker, env)
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(tmp_root, ignore_errors=True)

    if not ret:
        raise RuntimeError(ret_msg or "115 cloud transfer failed")
    return f"Transfer completed; media={len(media_files)}, subtitles={len(subtitle_files)}, deleted_extras={cleanup_count}"


def cloud115_record_result(cfg, status, message):
    from datetime import datetime

    cfg["last_status"] = bool(status)
    cfg["last_message"] = str(message)
    cfg["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cloud115_save_config(cfg)


def cloud115_scheduler_loop():
    import time

    global CLOUD115_RUNNING
    while True:
        try:
            cfg = cloud115_load_config()
            enabled = bool(cfg.get("auto_enabled"))
            interval = int(cfg.get("interval_minutes") or 60)
            if enabled and interval > 0 and not CLOUD115_RUNNING:
                CLOUD115_RUNNING = True
                try:
                    message = cloud115_execute(cfg)
                    cloud115_record_result(cfg, True, message)
                except Exception as err:
                    cloud115_record_result(cfg, False, err)
                finally:
                    CLOUD115_RUNNING = False
            time.sleep(max(interval, 1) * 60 if enabled else 30)
        except Exception:
            time.sleep(30)


def cloud115_start_scheduler():
    import threading

    global CLOUD115_SCHEDULER_STARTED
    if CLOUD115_SCHEDULER_STARTED:
        return
    CLOUD115_SCHEDULER_STARTED = True
    thread = threading.Thread(target=cloud115_scheduler_loop, daemon=True)
    thread.start()


@App.route('/cloud115', methods=['POST', 'GET'])
def cloud115():
    """
    Standalone 115 cloud transfer panel.
    """
    cloud115_start_scheduler()
    cfg = cloud115_load_config()
    message = None
    status = None
    if request.method == "POST":
        action = request.form.get("action", "save")
        cookie = cloud115_normalize_cookie(request.form.get("cookie", ""))
        if cookie:
            cfg["cookie"] = cookie
        cfg["source_path"] = request.form.get("source_path", cfg.get("source_path", "")).strip()
        cfg["target_path"] = request.form.get("target_path", cfg.get("target_path", "")).strip()
        cfg["delay_seconds"] = float(request.form.get("delay_seconds", cfg.get("delay_seconds", 2)) or 0)
        cfg["jitter_seconds"] = float(request.form.get("jitter_seconds", cfg.get("jitter_seconds", 1)) or 0)
        cfg["cooldown_seconds"] = float(request.form.get("cooldown_seconds", cfg.get("cooldown_seconds", 90)) or 0)
        cfg["retry_times"] = int(request.form.get("retry_times", cfg.get("retry_times", 4)) or 1)
        cfg["interval_minutes"] = int(request.form.get("interval_minutes", cfg.get("interval_minutes", 60)) or 60)
        cfg["check_for_relogin"] = request.form.get("check_for_relogin") == "on"
        cfg["auto_enabled"] = request.form.get("auto_enabled") == "on"
        cfg["delete_extras"] = request.form.get("delete_extras") == "on"
        cloud115_save_config(cfg)
        if action == "run":
            global CLOUD115_RUNNING
            if CLOUD115_RUNNING:
                status = False
                message = "A transfer task is already running"
            else:
                CLOUD115_RUNNING = True
                try:
                    message = cloud115_execute(cfg)
                    status = True
                    cloud115_record_result(cfg, True, message)
                except Exception as err:
                    status = False
                    message = str(err)
                    cloud115_record_result(cfg, False, message)
                finally:
                    CLOUD115_RUNNING = False
        else:
            status = True
            message = "Settings saved"
    return render_template(
        "cloud115.html",
        Config=cfg,
        HasCookie=bool(cfg.get("cookie")),
        CookieFingerprint=cloud115_cookie_fingerprint(cfg.get("cookie", "")),
        Status=status,
        Message=message,
    )


@App.route('/cloud115/list', methods=['POST'])
def cloud115_list():
    import json as jsonlib
    import os
    import subprocess

    cfg = cloud115_load_config()
    cookie = cloud115_normalize_cookie(request.form.get("cookie", "")) or cloud115_normalize_cookie(cfg.get("cookie", ""))
    path = request.form.get("path", "/").strip() or "/"
    env = os.environ.copy()
    if cookie:
        env["CLOUD115_COOKIES"] = cookie
        env.pop("CLOUD115_COOKIE_FILE", None)
    env["CLOUD115_DELAY_SECONDS"] = str(cfg.get("delay_seconds") or 0)
    env["CLOUD115_JITTER_SECONDS"] = str(cfg.get("jitter_seconds") or 0)
    env["CLOUD115_COOLDOWN_SECONDS"] = str(cfg.get("cooldown_seconds") or 0)
    env["CLOUD115_RETRY_TIMES"] = str(cfg.get("retry_times") or 1)
    env["CLOUD115_CHECK_FOR_RELOGIN"] = "true" if cfg.get("check_for_relogin", True) else "false"
    env["CLOUD115_COOKIE_STORE"] = "/config/cloud115.cookie"
    python = env.get("CLOUD115_PYTHON", "/opt/python312/bin/python3.12")
    worker = env.get("CLOUD115_WORKER", "/nas-tools/app/utils/cloud115_worker.py")
    proc = subprocess.run(
        [python, worker, "list", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    body = (proc.stdout or "").strip()
    if proc.returncode != 0:
        body = jsonlib.dumps({
            "ok": False,
            "message": (proc.stderr or body or "Failed to read 115 path").strip(),
        }, ensure_ascii=False)
    return body, 200, {"Content-Type": "application/json; charset=utf-8"}


@App.route('/cloud115/test', methods=['POST'])
def cloud115_test():
    import json as jsonlib
    import os
    import subprocess

    cfg = cloud115_load_config()
    cookie = cloud115_normalize_cookie(request.form.get("cookie", "")) or cloud115_normalize_cookie(cfg.get("cookie", ""))
    env = os.environ.copy()
    if cookie:
        env["CLOUD115_COOKIES"] = cookie
        env.pop("CLOUD115_COOKIE_FILE", None)
    env["CLOUD115_DELAY_SECONDS"] = str(cfg.get("delay_seconds") or 0)
    env["CLOUD115_JITTER_SECONDS"] = str(cfg.get("jitter_seconds") or 0)
    env["CLOUD115_COOLDOWN_SECONDS"] = str(cfg.get("cooldown_seconds") or 0)
    env["CLOUD115_RETRY_TIMES"] = str(cfg.get("retry_times") or 1)
    env["CLOUD115_CHECK_FOR_RELOGIN"] = "true" if cfg.get("check_for_relogin", True) else "false"
    env["CLOUD115_COOKIE_STORE"] = "/config/cloud115.cookie"
    python = env.get("CLOUD115_PYTHON", "/opt/python312/bin/python3.12")
    worker = env.get("CLOUD115_WORKER", "/nas-tools/app/utils/cloud115_worker.py")
    proc = subprocess.run(
        [python, worker, "test"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    body = (proc.stdout or "").strip()
    if proc.returncode != 0:
        body = jsonlib.dumps({
            "ok": False,
            "message": (proc.stderr or body or "Cookie test failed").strip(),
        }, ensure_ascii=False)
    return body, 200, {"Content-Type": "application/json; charset=utf-8"}


cloud115_start_scheduler()
'''


def main():
    text = MAIN.read_text(encoding="utf-8")
    if "@App.route('/cloud115'" not in text:
        anchor = "@App.route('/do', methods=['POST'])"
        if anchor not in text:
            raise RuntimeError("Could not find /do route anchor in web/main.py")
        MAIN.write_text(text.replace(anchor, ROUTE + "\n" + anchor, 1), encoding="utf-8")

    nav_text = NAVBAR.read_text(encoding="utf-8")
    if 'page: "cloud115"' in nav_text:
        return
    menu_item = r'''
  {
    name: "115 Cloud Transfer",
    page: "cloud115",
    icon: html`
      <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-cloud-upload" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
        <path d="M7 18a4.6 4.4 0 0 1 0 -9a5 4.5 0 0 1 9.7 -1.5a4.5 4.5 0 0 1 2.3 8.5"></path>
        <path d="M12 12l0 9"></path>
        <path d="M9 15l3 -3l3 3"></path>
      </svg>
    `,
  },
'''
    anchor = '    page: "service",'
    index = nav_text.find(anchor)
    if index == -1:
        raise RuntimeError("Could not find service menu anchor in navbar index.js")
    object_start = nav_text.rfind("  {", 0, index)
    if object_start == -1:
        raise RuntimeError("Could not find service menu object start in navbar index.js")
    nav_text = nav_text[:object_start] + menu_item + nav_text[object_start:]
    NAVBAR.write_text(nav_text, encoding="utf-8")


if __name__ == "__main__":
    main()
    print("NASTool cloud115 panel patch applied.")
