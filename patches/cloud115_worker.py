import json
import os
import posixpath
import sys
import time
from functools import lru_cache

import requests


class Cloud115Error(Exception):
    pass


class Cloud115Mover:
    def __init__(self):
        self.cookies = self._load_cookies()
        self.src_prefix = os.getenv("CLOUD115_SRC_PREFIX", "").rstrip("/\\")
        self.remote_src_root = self._clean_remote_dir(os.getenv("CLOUD115_REMOTE_SRC_ROOT", ""))
        self.on_conflict = os.getenv("CLOUD115_ON_CONFLICT", "fail").strip().lower()
        self.delay = float(os.getenv("CLOUD115_DELAY_SECONDS", "1.5") or "0")
        if not self.cookies:
            raise Cloud115Error("CLOUD115_COOKIES or CLOUD115_COOKIE_FILE is not configured")

        from p115client.client import P115Client

        self.client = P115Client(cookies=self.cookies)
        self._headers = {
            "Cookie": self.cookies,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def move(self, src, dest):
        if not self.src_prefix or not self.remote_src_root:
            raise Cloud115Error("CLOUD115_SRC_PREFIX and CLOUD115_REMOTE_SRC_ROOT are required")
        src_remote = self._local_to_remote(src)
        dest_remote = self._dest_to_remote(dest)
        dest_dir = posixpath.dirname(dest_remote)
        dest_name = posixpath.basename(dest_remote)

        src_parent = posixpath.dirname(src_remote)
        src_name = posixpath.basename(src_remote)
        src_parent_id = self._resolve_dir(src_parent)
        src_file = self._find_child(src_parent_id, src_name, want_dir=False)
        if not src_file:
            raise Cloud115Error(f"115 source file not found: {src_remote}")

        dest_parent_id = self._ensure_dir(dest_dir)
        existing = self._find_child(dest_parent_id, dest_name, want_dir=False)
        if existing:
            if self.on_conflict == "skip":
                return f"target already exists, skipped: {dest_remote}"
            raise Cloud115Error(f"115 target file already exists: {dest_remote}")

        file_id = str(src_file["id"])
        self._move_file(file_id, dest_parent_id)
        if src_name != dest_name:
            self._rename_file(file_id, dest_name)
        self._sleep()
        return {
            "source": src_remote,
            "target": dest_remote,
        }

    def list_path(self, path):
        cid = self._resolve_dir(path)
        items = sorted(
            self._list_dir(cid),
            key=lambda item: (not item["is_dir"], item["name"].lower()),
        )
        return {
            "path": self._clean_remote_dir(path),
            "items": items,
        }

    def walk_path(self, path):
        path = self._clean_remote_dir(path)
        cid = self._resolve_dir(path)
        files = []
        self._walk_dir(cid, path, files)
        return {"path": path, "files": files}

    def _walk_dir(self, cid, path, files):
        for item in self._list_dir(str(cid)):
            item_path = posixpath.join(path, item["name"])
            if item["is_dir"]:
                self._walk_dir(item["id"], item_path, files)
            else:
                files.append({
                    "path": item_path,
                    "name": item["name"],
                    "id": item["id"],
                })

    def _load_cookies(self):
        cookies = os.getenv("CLOUD115_COOKIES", "").strip()
        if cookies:
            return cookies
        cookie_file = os.getenv("CLOUD115_COOKIE_FILE", "").strip()
        if cookie_file and os.path.exists(cookie_file):
            with open(cookie_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def _local_to_remote(self, src):
        return self._map_local_to_remote(src, self.src_prefix, self.remote_src_root, "source")

    def _dest_to_remote(self, dest):
        dest_prefix = os.getenv("CLOUD115_DEST_PREFIX", "").rstrip("/\\")
        remote_dest_root = self._clean_remote_dir(os.getenv("CLOUD115_REMOTE_DEST_ROOT", ""))
        if dest_prefix and remote_dest_root:
            return self._map_local_to_remote(dest, dest_prefix, remote_dest_root, "target")
        return self._clean_remote_file(dest)

    def _map_local_to_remote(self, local_path, local_prefix, remote_root, label):
        src_norm = os.path.normpath(local_path)
        prefix_norm = os.path.normpath(local_prefix)
        try:
            rel = os.path.relpath(src_norm, prefix_norm)
        except ValueError as err:
            raise Cloud115Error(f"{label} path is outside configured prefix: {local_path}") from err
        if rel == "." or rel.startswith(".."):
            raise Cloud115Error(f"{label} path is outside configured prefix: {local_path}")
        rel = rel.replace("\\", "/")
        return self._clean_remote_file(posixpath.join(remote_root, rel))

    @staticmethod
    def _clean_remote_dir(path):
        path = (path or "").replace("\\", "/").strip()
        if not path.startswith("/"):
            path = "/" + path
        return posixpath.normpath(path)

    @classmethod
    def _clean_remote_file(cls, path):
        path = cls._clean_remote_dir(path)
        if path == "/":
            raise Cloud115Error("target file path cannot be root")
        return path

    def _normalize(self, item):
        data = item or {}
        file_id = (
            data.get("id")
            or data.get("fid")
            or data.get("file_id")
            or data.get("cid")
            or data.get("cate_id")
        )
        name = (
            data.get("name")
            or data.get("file_name")
            or data.get("n")
            or data.get("fn")
            or ""
        )
        is_dir = data.get("is_dir")
        if is_dir is None:
            is_dir = data.get("is_directory")
        if is_dir is None:
            is_dir = data.get("type") == 1 or data.get("fc") == "0" or bool(data.get("cid") and not data.get("fid"))
        return {
            "id": str(file_id),
            "name": str(name),
            "is_dir": bool(is_dir),
        }

    @lru_cache(maxsize=4096)
    def _list_dir(self, cid):
        from p115client.client import check_response

        items = []
        offset = 0
        limit = 1000
        while True:
            resp = self.client.fs_files_app({
                "cid": int(cid),
                "limit": limit,
                "offset": offset,
                "show_dir": 1,
            })
            check_response(resp)
            page = resp.get("data", [])
            items.extend(self._normalize(item) for item in page)
            if len(page) < limit:
                break
            offset += limit
        return tuple(items)

    def _find_child(self, cid, name, want_dir=None):
        for item in self._list_dir(str(cid)):
            if item["name"] != name:
                continue
            if want_dir is not None and item["is_dir"] != want_dir:
                continue
            return item
        return None

    def _resolve_dir(self, path):
        path = self._clean_remote_dir(path)
        if path == "/":
            return "0"
        cid = "0"
        for part in [p for p in path.split("/") if p]:
            item = self._find_child(cid, part, want_dir=True)
            if not item:
                raise Cloud115Error(f"115 directory not found: {path}")
            cid = item["id"]
        return cid

    def _ensure_dir(self, path):
        path = self._clean_remote_dir(path)
        if path == "/":
            return "0"
        cid = "0"
        for part in [p for p in path.split("/") if p]:
            item = self._find_child(cid, part, want_dir=True)
            if item:
                cid = item["id"]
                continue
            cid = self._mkdir(cid, part)
            self._list_dir.cache_clear()
        return cid

    def _mkdir(self, parent_id, name):
        method = getattr(self.client, "fs_mkdir_app", None)
        if method:
            resp = method(name, pid=int(parent_id), app="android")
            return self._extract_created_id(resp, parent_id, name)

        method = getattr(self.client, "fs_mkdir", None)
        if method:
            resp = method(name, pid=int(parent_id))
            return self._extract_created_id(resp, parent_id, name)

        resp = requests.post(
            "https://webapi.115.com/files/add",
            data={"pid": parent_id, "cname": name},
            headers=self._headers,
            timeout=30,
        ).json()
        if not resp.get("state", False):
            raise Cloud115Error(f"failed to create 115 directory {name}: {resp}")
        return self._extract_created_id(resp, parent_id, name)

    def _extract_created_id(self, resp, parent_id, name):
        if isinstance(resp, dict):
            data = resp.get("data") or resp
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict):
                for key in ("cid", "file_id", "id", "fid", "cate_id"):
                    if data.get(key):
                        return str(data[key])
        for _ in range(5):
            self._list_dir.cache_clear()
            item = self._find_child(str(parent_id), name, want_dir=True)
            if item:
                return item["id"]
            time.sleep(0.6)
        raise Cloud115Error(f"created directory was not found: {name}; response={resp}")

    def _move_file(self, file_id, dest_parent_id):
        from p115client.client import check_response

        errors = []
        for call in (
            lambda: self.client.fs_move_app(str(file_id), pid=int(dest_parent_id), app="android"),
            lambda: self.client.fs_move(str(file_id), pid=int(dest_parent_id)),
        ):
            try:
                resp = call()
                check_response(resp)
                self._list_dir.cache_clear()
                self._sleep()
                return
            except Exception as err:
                errors.append(str(err))
        resp = requests.post(
            "https://webapi.115.com/files/move",
            data={"ids": str(file_id), "to_cid": int(dest_parent_id)},
            headers=self._headers,
            timeout=30,
        ).json()
        if not resp.get("state", False):
            raise Cloud115Error(f"failed to move 115 file: {resp}; previous={errors}")
        self._list_dir.cache_clear()
        self._sleep()

    def _rename_file(self, file_id, new_name):
        method = getattr(self.client, "fs_rename_app", None)
        if method:
            resp = method((str(file_id), new_name), app="android")
            self._check_optional_response(resp, "failed to rename 115 file")
            self._list_dir.cache_clear()
            self._sleep()
            return

        method = getattr(self.client, "fs_rename", None)
        if method:
            resp = method((str(file_id), new_name))
            self._check_optional_response(resp, "failed to rename 115 file")
            self._list_dir.cache_clear()
            self._sleep()
            return

        for method_name in ("fs_rename_open", "fs_update_open"):
            method = getattr(self.client, method_name, None)
            if not method:
                continue
            resp = method({"file_id": str(file_id), "file_name": new_name})
            self._check_optional_response(resp, "failed to rename 115 file")
            self._list_dir.cache_clear()
            self._sleep()
            return

        resp = requests.post(
            "https://webapi.115.com/files/edit",
            data={"fid": str(file_id), "file_name": new_name},
            headers=self._headers,
            timeout=30,
        ).json()
        self._check_optional_response(resp, "failed to rename 115 file")
        self._list_dir.cache_clear()
        self._sleep()

    def _delete_file(self, file_id):
        from p115client.client import check_response

        errors = []
        for call in (
            lambda: self.client.fs_delete_app(str(file_id), app="android"),
            lambda: self.client.fs_delete(str(file_id)),
        ):
            try:
                resp = call()
                check_response(resp)
                self._list_dir.cache_clear()
                self._sleep()
                return
            except Exception as err:
                errors.append(str(err))
        raise Cloud115Error(f"failed to delete 115 file: {file_id}; previous={errors}")

    def delete_path(self, path):
        path = self._clean_remote_file(path)
        parent = posixpath.dirname(path)
        name = posixpath.basename(path)
        parent_id = self._resolve_dir(parent)
        item = self._find_child(parent_id, name, want_dir=False)
        if not item:
            return f"not found, skipped: {path}"
        self._delete_file(item["id"])
        return f"deleted: {path}"

    def _sleep(self):
        if self.delay > 0:
            time.sleep(self.delay)

    @staticmethod
    def _check_optional_response(resp, message):
        if isinstance(resp, dict) and resp.get("state", True) is False:
            raise Cloud115Error(f"{message}: {resp}")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        path = sys.argv[2] if len(sys.argv) >= 3 else "/"
        result = Cloud115Mover().list_path(path)
        result["ok"] = True
        print(json.dumps(result, ensure_ascii=False))
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "walk":
        path = sys.argv[2] if len(sys.argv) >= 3 else "/"
        result = Cloud115Mover().walk_path(path)
        result["ok"] = True
        print(json.dumps(result, ensure_ascii=False))
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "test":
        Cloud115Mover().list_path("/")
        print(json.dumps({"ok": True, "message": "115 Cookie 可用"}, ensure_ascii=False))
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "delete":
        message = Cloud115Mover().delete_path(sys.argv[2])
        print(json.dumps({"ok": True, "message": message}, ensure_ascii=False))
        return
    if len(sys.argv) == 3:
        message = Cloud115Mover().move(sys.argv[1], sys.argv[2])
        print(json.dumps({"ok": True, "message": message}, ensure_ascii=False))
        return
    raise SystemExit("usage: cloud115_worker.py SRC DEST | list PATH | test")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(json.dumps({"ok": False, "message": str(err)}, ensure_ascii=False))
