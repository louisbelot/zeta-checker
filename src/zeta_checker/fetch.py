from __future__ import annotations

import hashlib
import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

CHUNK = 1 << 20
AGENT = "zeta-checker/0.1"
RETRY_CODES = {408, 425, 429, 500, 502, 503, 504}
TRANSIENT = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError)


class FetchError(RuntimeError):
    pass


@dataclass
class Source:
    name: str
    url: str
    size: int | None = None
    sha256: str | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class Status:
    name: str
    state: str
    size: int
    sha256: str
    detail: str = ""


def load(path: Path) -> list[Source]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**entry) for entry in data["sources"]]


def save(path: Path, sources: list[Source]) -> None:
    body = {"sources": [asdict(s) for s in sources]}
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def _total(headers, resumed: bool) -> int | None:
    if resumed:
        rng = headers.get("Content-Range") or ""
        tail = rng.rpartition("/")[2]
        return int(tail) if tail.isdigit() else None
    n = headers.get("Content-Length")
    return int(n) if n and n.isdigit() else None


def _meta(headers) -> dict:
    return {"etag": headers.get("ETag"), "last_modified": headers.get("Last-Modified")}


def download(
    url: str,
    dest: Path,
    *,
    opener: Callable = urllib.request.urlopen,
    retries: int = 4,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = 60,
) -> dict:
    tmp = dest.with_name(dest.name + ".partial")
    for attempt in range(retries + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = {"User-Agent": AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with opener(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
                resumed = have > 0 and resp.status == 206
                expected = _total(resp.headers, resumed)
                meta = _meta(resp.headers)
                with tmp.open("ab" if resumed else "wb") as out:
                    while block := resp.read(CHUNK):
                        out.write(block)
            size = tmp.stat().st_size
            if expected is not None and size != expected:
                raise http.client.IncompleteRead(b"", expected - size)
            tmp.replace(dest)
            return meta | {"size": size}
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:
                total = _total(e.headers, True)
                if total == have:
                    tmp.replace(dest)
                    return _meta(e.headers) | {"size": have}
                tmp.unlink()
            elif e.code not in RETRY_CODES or attempt == retries:
                raise FetchError(f"{url}: HTTP {e.code}") from e
        except TRANSIENT as e:
            if attempt == retries:
                raise FetchError(f"{url}: {e!r} after {retries + 1} attempts") from e
        sleep(backoff * 2**attempt)
    raise FetchError(f"{url}: gave up after {retries + 1} attempts")


def head(url: str, *, opener: Callable = urllib.request.urlopen, timeout: float = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT}, method="HEAD")
    with opener(req, timeout=timeout) as resp:
        n = resp.headers.get("Content-Length")
        return _meta(resp.headers) | {"size": int(n) if n and n.isdigit() else None}


def remote_sha256(url: str, *, opener: Callable = urllib.request.urlopen) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with opener(req, timeout=60) as resp:
        while block := resp.read(CHUNK):
            h.update(block)
            size += len(block)
    return size, h.hexdigest()


def sync(
    sources: list[Source],
    root: Path,
    *,
    record: bool = False,
    opener: Callable = urllib.request.urlopen,
    **kw,
) -> list[Status]:
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for src in sources:
        path = root / src.name
        fetched = None
        if not path.exists():
            fetched = download(src.url, path, opener=opener, **kw)
        size, digest = path.stat().st_size, sha256(path)
        if src.sha256 is None:
            state = "new"
            if record:
                meta = fetched or head(src.url, opener=opener)
                src.size, src.sha256 = size, digest
                src.etag, src.last_modified = meta["etag"], meta["last_modified"]
                state = "recorded"
        elif (size, digest) != (src.size, src.sha256):
            state = "changed"
        else:
            state = "downloaded" if fetched else "ok"
        out.append(Status(src.name, state, size, digest))
    return out


def upstream(sources: list[Source], *, opener: Callable = urllib.request.urlopen) -> list[Status]:
    out = []
    for src in sources:
        meta = head(src.url, opener=opener)
        diffs = []
        for key in ("etag", "last_modified", "size"):
            old, new = getattr(src, key), meta[key]
            if old is not None and new is not None and old != new:
                diffs.append(f"{key} {old!r} -> {new!r}")
        state = "changed" if diffs else "same"
        out.append(Status(src.name, state, src.size or 0, src.sha256 or "", "; ".join(diffs)))
    return out


def rehash(sources: list[Source], *, opener: Callable = urllib.request.urlopen) -> list[Status]:
    out = []
    for src in sources:
        size, digest = remote_sha256(src.url, opener=opener)
        state = "same" if (size, digest) == (src.size, src.sha256) else "changed"
        out.append(Status(src.name, state, size, digest))
    return out
