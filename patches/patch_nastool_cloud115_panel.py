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
        source_path = request.form.get("source_path", "").strip()
        target_path = request.form.get("target_path", "").strip()
        if not source_path:
            status = False
            message = "源目录不能为空"
        elif not target_path:
            status = False
            message = "目标目录不能为空"
        else:
            try:
                from app.filetransfer import FileTransfer

                FileTransfer().transfer_manually(source_path, target_path, "cloud115")
                status = True
                message = "115云端转移任务已执行，请查看后台日志确认每个文件结果。"
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
