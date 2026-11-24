"""Publish the card's PNG review evidence to Plane before handing it to a reviewer."""
import hashlib
import html
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


def screenshots(root, identifier):
    # Open every component relative to a trusted directory. A card checkout may
    # contain symlinks. Only regular PNGs in this card's evidence directory qualify.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, flags)
    try:
        for part in (identifier, "tmp", "review", identifier):
            if not part or part in (".", "..") or "/" in part:
                raise ValueError("Invalid evidence directory")
            try:
                child = os.open(part, flags, dir_fd=directory)
            except FileNotFoundError:
                return
            os.close(directory)
            directory = child
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(".png"):
                continue
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError(f"Expected regular screenshot: {name}")
                if info.st_size > 5 * 1024 * 1024:
                    raise ValueError(f"Resize screenshot to 5 MiB or less: {name}")
                data = stream.read(info.st_size + 1)
                if len(data) != info.st_size or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError(f"Invalid PNG: {name}")
            yield name, data
    finally:
        os.close(directory)


def send_file(upload, data, origin):
    # The local Plane proxy also serves its object store. Do not forward the
    # tracker token to object storage or accept cross-origin upload locations.
    target = urljoin(origin, upload["url"])
    if urlsplit(target)[:2] != urlsplit(origin)[:2]:
        raise ValueError("Expected a same-origin Plane upload URL")
    boundary = uuid4().hex
    parts = []
    for key, value in upload["fields"].items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="screenshot.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),
              data, f'\r\n--{boundary}--\r\n'.encode()]
    with urlopen(Request(target, data=b"".join(parts), headers={"Content-Type": "multipart/form-data; boundary=" + boundary}), timeout=45):
        pass


def publish(root, identifier, base, origin, key):
    def api(path, method="GET", body=None):
        req = Request(base + path, method=method, headers={"X-API-Key": key, "Content-Type": "application/json"},
                      data=json.dumps(body).encode() if body is not None else None)
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    images = []
    source = "symphony-review"
    known = None
    for name, data in screenshots(root, identifier):
        digest = hashlib.sha256(data).hexdigest()
        if known is None:
            known = {(a["attributes"]["name"], (a["external_id"] or "").split(":")[0]): a["id"]
                     for a in api("attachments/") if a.get("external_source") == source}
        asset_id = known.get((name, digest))
        if not asset_id:
            record = api("attachments/", "POST", {"name": name, "type": "image/png", "size": len(data),
                         "external_source": source, "external_id": digest + ":" + uuid4().hex})
            asset_id = record["asset_id"]
            send_file(record["upload_data"], data, origin)
            api("attachments/" + asset_id + "/", "PATCH", {"is_uploaded": True})
        workspace_path = urlsplit(base).path.replace("/api/v1/", "/api/assets/v2/", 1).replace("/work-items/", "/issues/")
        url = origin.rstrip("/") + workspace_path + "attachments/" + asset_id + "/"
        caption = html.escape(Path(name).stem.replace("-", " ").replace("_", " ").capitalize())
        images.append(f'<p><strong>{caption}</strong></p><img src="{html.escape(url, quote=True)}" alt="{caption}" width="100%">')
    if not images:
        return 0
    markup = "<p><strong>Review screenshots</strong></p>" + "".join(images)
    external_id = "gallery:" + hashlib.sha256((base + markup).encode()).hexdigest()
    path = "comments/"
    while path:
        page = api(path)
        if any(c.get("external_id") == external_id and c.get("external_source") == source for c in page["results"]):
            return len(images)
        path = "comments/?cursor=" + quote(page["next_cursor"], safe="") if page["next_page_results"] else None
    api("comments/", "POST", {"comment_html": markup, "external_source": source, "external_id": external_id})
    return len(images)


if __name__ == "__main__":
    root, identifier, base, origin = sys.argv[1:]
    try:
        print(publish(root, identifier, base, origin, os.environ["PLANE_API_KEY"]))
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(f"Review screenshots: {exc}")
