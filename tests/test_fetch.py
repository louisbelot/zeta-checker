import email.message
import hashlib
import io
import urllib.error

import pytest

from zeta_checker import fetch

DATA = bytes(range(256)) * 40


class Response:
    def __init__(self, status, body, headers, drop_at=None):
        self.status = status
        self.headers = email.message.Message()
        for k, v in headers.items():
            self.headers[k] = v
        self._body = io.BytesIO(body)
        self._drop_at = drop_at

    def read(self, n=-1):
        if self._drop_at is not None and self._body.tell() >= self._drop_at:
            raise ConnectionResetError("dropped")
        if self._drop_at is not None:
            n = min(n, self._drop_at - self._body.tell())
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Server:
    def __init__(self, data=DATA, ranges=True, script=()):
        self.data = data
        self.ranges = ranges
        self.script = list(script)
        self.calls = []

    def __call__(self, req, timeout=None):
        rng = req.get_header("Range")
        self.calls.append((req.get_method(), rng))
        action = self.script.pop(0) if self.script else "ok"
        if isinstance(action, int):
            raise urllib.error.HTTPError(req.full_url, action, "err", email.message.Message(), None)
        headers = {"ETag": '"v1"', "Last-Modified": "Fri, 20 Nov 2026 18:18:35 GMT"}
        if req.get_method() == "HEAD":
            return Response(200, b"", headers | {"Content-Length": str(len(self.data))})
        start = int(rng[6:-1]) if rng and self.ranges else 0
        body = self.data[start:]
        if start:
            headers["Content-Range"] = f"bytes {start}-{len(self.data) - 1}/{len(self.data)}"
        headers["Content-Length"] = str(len(body) if action != "short" else len(body) + 10)
        drop = len(body) // 3 if action == "drop" else None
        return Response(206 if start else 200, body, headers, drop_at=drop)


def run(server, path, **kw):
    return fetch.download("https://example.test/f", path, opener=server, sleep=lambda s: None, **kw)


def test_clean_download(tmp_path):
    meta = run(Server(), tmp_path / "f")
    assert (tmp_path / "f").read_bytes() == DATA
    assert meta["size"] == len(DATA) and meta["etag"] == '"v1"'
    assert not (tmp_path / "f.partial").exists()


def test_resume_after_drop(tmp_path):
    server = Server(script=["drop"])
    run(server, tmp_path / "f")
    assert (tmp_path / "f").read_bytes() == DATA
    assert server.calls[0][1] is None
    assert server.calls[1][1] == f"bytes={len(DATA) // 3}-"


def test_restart_when_range_ignored(tmp_path):
    server = Server(ranges=False, script=["drop"])
    run(server, tmp_path / "f")
    assert (tmp_path / "f").read_bytes() == DATA


def test_short_body_is_retried(tmp_path):
    server = Server(script=["short"])
    run(server, tmp_path / "f")
    assert (tmp_path / "f").read_bytes() == DATA
    assert len(server.calls) == 2


def test_not_found_fails_fast(tmp_path):
    server = Server(script=[404])
    with pytest.raises(fetch.FetchError, match="404"):
        run(server, tmp_path / "f")
    assert len(server.calls) == 1


def test_server_error_is_retried(tmp_path):
    slept = []
    server = Server(script=[503, 503])
    fetch.download("https://example.test/f", tmp_path / "f", opener=server, sleep=slept.append)
    assert slept == [1.0, 2.0]
    assert (tmp_path / "f").read_bytes() == DATA


def test_gives_up(tmp_path):
    server = Server(script=[503] * 3)
    with pytest.raises(fetch.FetchError):
        run(server, tmp_path / "f", retries=2)
    assert len(server.calls) == 3


def test_sync_records_then_verifies(tmp_path):
    manifest = tmp_path / "manifest.json"
    fetch.save(manifest, [fetch.Source("f.bin", "https://example.test/f")])
    server = Server()
    sources = fetch.load(manifest)
    assert [s.state for s in fetch.sync(sources, tmp_path / "dl", opener=server)] == ["new"]
    rows = fetch.sync(sources, tmp_path / "dl", record=True, opener=server)
    assert rows[0].state == "recorded"
    fetch.save(manifest, sources)
    again = fetch.load(manifest)
    assert again[0].sha256 == hashlib.sha256(DATA).hexdigest()
    assert again[0].etag == '"v1"'
    assert fetch.sync(again, tmp_path / "dl", opener=server)[0].state == "ok"
    (tmp_path / "dl" / "f.bin").write_bytes(DATA[:-1] + b"x")
    assert fetch.sync(again, tmp_path / "dl", opener=server)[0].state == "changed"


def test_upstream_flags_new_etag(tmp_path):
    src = fetch.Source("f", "https://example.test/f", len(DATA), "0" * 64, '"v0"', None)
    rows = fetch.upstream([src], opener=Server())
    assert rows[0].state == "changed"
    assert '"v0"' in rows[0].detail and '"v1"' in rows[0].detail
    src.etag = '"v1"'
    assert fetch.upstream([src], opener=Server())[0].state == "same"


def test_rehash_matches_local(tmp_path):
    src = fetch.Source("f", "https://example.test/f", len(DATA), hashlib.sha256(DATA).hexdigest())
    assert fetch.rehash([src], opener=Server())[0].state == "same"
    src.sha256 = "0" * 64
    assert fetch.rehash([src], opener=Server())[0].state == "changed"
