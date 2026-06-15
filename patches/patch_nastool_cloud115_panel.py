from pathlib import Path


MAIN = Path("/nas-tools/web/main.py")
NAVBAR = Path("/nas-tools/web/static/components/layout/navbar/index.js")


ROUTE = r'''

@App.route('/cloud115', methods=['POST', 'GET'])
def cloud115():
    """
    Standalone 115 cloud transfer panel.
    It reuses NASTool manual recognition/naming and forces cloud115 transfer mode.
    """
    message = None
    status = None
    source_path = ""
    target_path = ""
    if request.method == "POST":
        cookie = request.form.get("cookie", "").strip()
        source_path = request.form.get("source_path", "").strip()
        target_path = request.form.get("target_path", "").strip()
        if cookie:
            import os
            os.environ["CLOUD115_COOKIES"] = cookie
        if not source_path:
            status = False
            message = "源目录不能为空"
        elif not target_path:
            status = False
            message = "目标目录不能为空"
        else:
            try:
                import json as jsonlib
                import os
                import posixpath
                import shutil
                import subprocess
                import tempfile
                from app.filetransfer import FileTransfer
                from app.utils.types import RmtMode, SyncType

                env = os.environ.copy()
                if cookie:
                    env["CLOUD115_COOKIES"] = cookie
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
                    raise RuntimeError((proc.stderr or proc.stdout or "读取115源目录失败").strip())
                walked = jsonlib.loads((proc.stdout or "{}").strip())
                if not walked.get("ok"):
                    raise RuntimeError(walked.get("message") or "读取115源目录失败")
                files = walked.get("files") or []
                if not files:
                    raise RuntimeError("源目录下没有可处理文件")

                tmp_root = tempfile.mkdtemp(prefix="cloud115-virtual-")
                virtual_src = os.path.join(tmp_root, "src")
                virtual_dst = os.path.join(tmp_root, "dst")
                os.makedirs(virtual_src, exist_ok=True)
                os.makedirs(virtual_dst, exist_ok=True)
                local_files = []
                remote_source = source_path.rstrip("/") or "/"
                for item in files:
                    remote_file = item.get("path") or ""
                    rel = posixpath.relpath(remote_file, remote_source).replace("/", os.sep)
                    local_file = os.path.join(virtual_src, rel)
                    os.makedirs(os.path.dirname(local_file), exist_ok=True)
                    with open(local_file, "wb") as fp:
                        fp.write(b"0")
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
                finally:
                    for key, value in old_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
                    shutil.rmtree(tmp_root, ignore_errors=True)
                status = bool(ret)
                message = ret_msg or ("115云端转移完成" if ret else "115云端转移失败")
            except Exception as err:
                status = False
                message = str(err)
    return render_template(
        "cloud115.html",
        SourcePath=source_path,
        TargetPath=target_path,
        Status=status,
        Message=message,
    )


@App.route('/cloud115/list', methods=['POST'])
def cloud115_list():
    import json as jsonlib
    import os
    import subprocess

    cookie = request.form.get("cookie", "").strip()
    path = request.form.get("path", "/").strip() or "/"
    env = os.environ.copy()
    if cookie:
        env["CLOUD115_COOKIES"] = cookie
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
            "message": (proc.stderr or body or "读取115目录失败").strip(),
        }, ensure_ascii=False)
    return body, 200, {"Content-Type": "application/json; charset=utf-8"}
'''


def main():
    text = MAIN.read_text(encoding="utf-8")
    if "@App.route('/cloud115'" in text:
        pass
    else:
        anchor = "@App.route('/do', methods=['POST'])"
        if anchor not in text:
            raise RuntimeError("Could not find /do route anchor in web/main.py")
        MAIN.write_text(text.replace(anchor, ROUTE + "\n" + anchor, 1), encoding="utf-8")

    nav_text = NAVBAR.read_text(encoding="utf-8")
    if 'page: "cloud115"' in nav_text:
        return
    menu_item = r'''
  {
    name: "115云端转移",
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
    anchor = '  {\n    name: "服务",\n    page: "service",'
    if anchor not in nav_text:
        anchor = '    page: "service",'
        index = nav_text.find(anchor)
        if index == -1:
            raise RuntimeError("Could not find service menu anchor in navbar index.js")
        object_start = nav_text.rfind("  {", 0, index)
        if object_start == -1:
            raise RuntimeError("Could not find service menu object start in navbar index.js")
        nav_text = nav_text[:object_start] + menu_item + nav_text[object_start:]
    else:
        nav_text = nav_text.replace(anchor, menu_item + anchor, 1)
    NAVBAR.write_text(nav_text, encoding="utf-8")


if __name__ == "__main__":
    main()
    print("NASTool cloud115 panel patch applied.")
