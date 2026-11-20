import gzip
import io
import tarfile

import pytest

from zeta_checker import archive, hatches


def make_tar(members: list[tuple[str, bytes | None, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, kind, data in members:
            info = tarfile.TarInfo(name)
            if kind is None:
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
                continue
            info.type = kind
            info.linkname = data.decode()
            tf.addfile(info)
    return buf.getvalue()


def split(blob: bytes, folder, size: int = 100, stem: str = "lean.tar.gz"):
    folder.mkdir(exist_ok=True)
    chunks = [blob[i : i + size] for i in range(0, len(blob), size)]
    for i, chunk in enumerate(chunks, 1):
        (folder / f"{stem}.part{i:02d}").write_bytes(chunk)
    return archive.parts(folder, stem)


CLEAN = [
    ("lean/lakefile.toml", None, b'name = "x"\n'),
    ("lean/src/A.lean", None, b"theorem a : True := trivial\n"),
    ("lean/src/B/C.lean", None, b"def c := 1\ndef d := 2"),
]


def test_parts_concatenate_in_order(tmp_path):
    blob = make_tar(CLEAN)
    paths = split(blob, tmp_path / "dl", size=37)
    assert len(paths) == -(-len(blob) // 37)
    with archive.stream(paths) as f:
        assert f.read() == blob


def test_missing_part_is_refused(tmp_path):
    paths = split(make_tar(CLEAN), tmp_path / "dl", size=50)
    paths[1].unlink()
    with pytest.raises(FileNotFoundError, match="not numbered"):
        archive.parts(tmp_path / "dl", "lean.tar.gz")


def test_clean_listing_and_extract(tmp_path):
    paths = split(make_tar(CLEAN), tmp_path / "dl")
    with archive.stream(paths) as f:
        found = archive.listing(f)
    assert found.clean and found.files == 3 and found.bytes == sum(len(d) for _, _, d in CLEAN)
    archive.extract(paths, tmp_path / "out", reserve=0)
    assert (tmp_path / "out/lean/src/B/C.lean").read_bytes() == b"def c := 1\ndef d := 2"
    with pytest.raises(FileExistsError):
        archive.extract(paths, tmp_path / "out", reserve=0)


def test_unsafe_members_block_extraction(tmp_path):
    bad = [
        ("lean/ok.lean", None, b"x"),
        ("lean/link", tarfile.SYMTYPE, b"/etc/passwd"),
        ("lean/hard", tarfile.LNKTYPE, b"lean/ok.lean"),
        ("../escape.lean", None, b"x"),
        ("/abs.lean", None, b"x"),
        ("lean/dev", tarfile.CHRTYPE, b""),
        ("lean/fifo", tarfile.FIFOTYPE, b""),
    ]
    paths = split(make_tar(bad), tmp_path / "dl")
    with archive.stream(paths) as f:
        found = archive.listing(f)
    reasons = sorted(r for _, r in found.unsafe)
    assert reasons == ["absolute", "device", "fifo", "hardlink", "parent", "symlink"]
    with pytest.raises(archive.UnsafeArchive, match="6 unsafe"):
        archive.extract(paths, tmp_path / "out", reserve=0)
    assert not (tmp_path / "out").exists()


def test_windows_names_and_collisions(tmp_path):
    members = [
        ("lean/src/Aux.lean", None, b"x"),
        ("lean/src/a:b.lean", None, b"x"),
        ("lean/src/Dots.", None, b"x"),
        ("lean/src/Case.lean", None, b"x"),
        ("lean/src/case.lean", None, b"y"),
        ("lean/src/Node", None, b"x"),
        ("lean/src/node/Child.lean", None, b"x"),
    ]
    paths = split(make_tar(members), tmp_path / "dl")
    with archive.stream(paths) as f:
        found = archive.listing(f)
    assert sorted(why for _, why in found.unportable) == ["character", "reserved", "trailing"]
    assert ("lean/src/Case.lean", "lean/src/case.lean") in found.collisions
    assert ("lean/src/Node", "lean/src/node/") in found.collisions
    with pytest.raises(archive.UnsafeArchive):
        archive.extract(paths, tmp_path / "out", reserve=0)


def test_disk_reserve_is_enforced(tmp_path):
    paths = split(make_tar(CLEAN), tmp_path / "dl")
    with pytest.raises(OSError, match="spare"):
        archive.extract(paths, tmp_path / "out", reserve=1 << 60)


def test_gzip_check(tmp_path):
    blob = make_tar(CLEAN)
    packed, unpacked, members = archive.gzip_check(io.BytesIO(blob))
    assert (packed, members) == (len(blob), 1)
    assert unpacked == len(gzip.decompress(blob))
    assert archive.gzip_check(io.BytesIO(blob + blob))[2] == 2
    with pytest.raises(archive.UnsafeArchive, match="inside a member"):
        archive.gzip_check(io.BytesIO(blob[:-20]))
    with pytest.raises(archive.UnsafeArchive, match="bad gzip"):
        archive.gzip_check(io.BytesIO(blob + b"garbage!"))


def test_inventory_counts(tmp_path):
    (tmp_path / "src/B").mkdir(parents=True)
    (tmp_path / "src/A.lean").write_bytes(b"a\nb\nc\n")
    (tmp_path / "src/B/C.lean").write_bytes(b"one\ntwo")
    (tmp_path / "README").write_bytes(b"")
    inv = archive.inventory(tmp_path, depth=1)
    assert (inv.files, inv.lines, inv.bytes) == (3, 5, 13)
    assert inv.by_ext[".lean"] == [2, 5, 13]
    assert inv.by_dir["src"] == [2, 5, 13]
    assert inv.largest[0] == (3, "src/A.lean")


def test_paths_longer_than_max_path(tmp_path):
    deep = "lean/" + "/".join(["d" * 40] * 7) + "/Deep.lean"
    paths = split(make_tar([(deep, None, b"theorem t : False := sorry\n")]), tmp_path / "dl", 4096)
    archive.extract(paths, tmp_path / "out", reserve=0)
    assert archive.inventory(tmp_path / "out").files == 1
    report = hatches.scan(tmp_path / "out")
    assert [(h.file, h.rule) for h in report.hits] == [(deep, "sorry")]


def test_inventory_from_the_stream_matches_disk(tmp_path):
    paths = split(make_tar(CLEAN), tmp_path / "dl")
    archive.extract(paths, tmp_path / "out", reserve=0)
    disk = archive.inventory(tmp_path / "out/lean", depth=1)
    streamed = archive.inventory_pairs(archive.read_members(paths, "lean"), depth=1)
    assert disk == streamed
    assert streamed.by_ext == {".toml": [1, 1, 11], ".lean": [2, 3, 49]}
