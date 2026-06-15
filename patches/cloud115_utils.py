import os
import posixpath
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
        if not self.cookies:
            raise Cloud115Error("CLOUD115_COOKIES or CLOUD115_COOKIE_FILE is not configured")
        if not self.src_prefix or not self.remote_src_root:
            raise Cloud115Error("CLOUD115_SRC_PREFIX and CLOUD115_REMOTE_SRC_ROOT are required")

        from p115client.client import P115Client

        self.client = P115Client(cookies=self.cookies)
        self._headers = {
            "Cookie": self.cookies,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def move(self, src, dest):
        src_remote = self._local_to_remote(src)
        dest_remote = self._clean_remote_file(dest)
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
                return 0, f"target already exists, skipped: {dest_remote}"
            raise Cloud115Error(f"115 target file already exists: {dest_remote}")

        file_id = str(src_file["id"])
        self._move_file(file_id, dest_parent_id)
        if src_name != dest_name:
            self._rename_file(file_id, dest_name)
        return 0, ""

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
        src_norm = os.path.normpath(src)
        prefix_norm = os.path.normpath(self.src_prefix)
        try:
            rel = os.path.relpath(src_norm, prefix_norm)
        except ValueError as err:
            raise Cloud115Error(f"source path is outside CLOUD115_SRC_PREFIX: {src}") from err
        if rel == "." or rel.startswith(".."):
            raise Cloud115Error(f"source path is outside CLOUD115_SRC_PREFIX: {src}")
        rel = rel.replace("\\", "/")
        return self._clean_remote_file(posixpath.join(self.remote_src_root, rel))

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
        from p115client.client import normalize_attr_simple

        data = normalize_attr_simple(item)
        return {
            "id": str(data["id"]),
            "name": data.get("name") or data.get("file_name") or "",
            "is_dir": bool(data.get("is_dir")),
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
        for method_name in ("fs_mkdir_app", "fs_mkdir"):
            method = getattr(self.client, method_name, None)
            if not method:
                continue
            try:
                resp = method({"pid": int(parent_id), "cname": name})
            except TypeError:
                resp = method(name, int(parent_id))
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
            for key in ("cid", "file_id", "id"):
                if data.get(key):
                    return str(data[key])
        self._list_dir.cache_clear()
        item = self._find_child(str(parent_id), name, want_dir=True)
        if not item:
            raise Cloud115Error(f"created directory was not found: {name}")
        return item["id"]

    def _move_file(self, file_id, dest_parent_id):
        from p115client.client import check_response

        resp = self.client.fs_move_app(
            {"ids": str(file_id), "to_cid": int(dest_parent_id)},
            app="android",
        )
        check_response(resp)
        self._list_dir.cache_clear()

    def _rename_file(self, file_id, new_name):
        for method_name in ("fs_rename_app", "fs_rename"):
            method = getattr(self.client, method_name, None)
            if not method:
                continue
            try:
                resp = method({"fid": str(file_id), "file_name": new_name})
            except TypeError:
                resp = method(str(file_id), new_name)
            self._check_optional_response(resp, "failed to rename 115 file")
            self._list_dir.cache_clear()
            return

        resp = requests.post(
            "https://webapi.115.com/files/edit",
            data={"fid": str(file_id), "file_name": new_name},
            headers=self._headers,
            timeout=30,
        ).json()
        self._check_optional_response(resp, "failed to rename 115 file")
        self._list_dir.cache_clear()

    @staticmethod
    def _check_optional_response(resp, message):
        if isinstance(resp, dict) and resp.get("state", True) is False:
            raise Cloud115Error(f"{message}: {resp}")
