import io
import json
import shutil
import tarfile

from zeta_checker.cli import main


def test_scan_command(fixtures, tmp_path, capsys):
    out = tmp_path / "hatches.json"
    assert main(["scan", str(fixtures / "lean"), "--json", str(out), "--show", "1"]) == 0
    text = capsys.readouterr().out
    assert "2 files" in text and "[critical] sorry" in text
    assert out.exists()


def test_config_command(fixtures, capsys):
    assert main(["config", str(fixtures / "project")]) == 0
    text = capsys.readouterr().out
    assert "toolchain: leanprover/lean4:v4.33.1" in text
    assert "modules matched by no lib: 1" in text and "Stray.Orphan" in text


def test_statements_command(fixtures, capsys):
    assert main(["statements", str(fixtures / "project")]) == 0
    text = capsys.readouterr().out
    assert "imports: Mathlib" in text
    assert "this is RiemannHypothesis itself" in text
    assert "statement unfolds ZetaZerosOnLine" in text
    assert "only here: `(`; only here: `: ℂ )`" in text
    assert "src/Proof/Shadow.lean:5  def riemannZeta" in text
    assert 'src/Proof/Shadow.lean:9  notation "RiemannHypothesis"' in text


def test_extract_command(tmp_path, capsys):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("lean/src/A.lean")
        info.size = 5
        tf.addfile(info, io.BytesIO(b"x\ny\n\n"))
    dl = tmp_path / "downloads"
    dl.mkdir()
    (dl / "lean.tar.gz.part01").write_bytes(buf.getvalue())
    assert main(["-w", str(tmp_path), "extract", "--list"]) == 0
    assert "1 members: 1 files" in capsys.readouterr().out
    assert main(["-w", str(tmp_path), "extract"]) == 0
    assert (tmp_path / "alpoge_lean/lean/src/A.lean").read_bytes() == b"x\ny\n\n"


def test_imports_command_splits_hatches(fixtures, tmp_path, capsys):
    project = tmp_path / "project"
    shutil.copytree(fixtures / "project", project)
    scan = tmp_path / "hatches.json"
    assert main(["scan", str(project), "--json", str(scan)]) == 0
    capsys.readouterr()
    out = tmp_path / "imports.json"
    assert main(["imports", str(project), "--hatches", str(scan), "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "import cone of Statements, Main: 3 modules" in text
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["hatches"]["critical sorry"] == [2, 2]
    assert body["hatches"]["low notation"] == [1, 0]


def test_archive_mode_matches_directory(fixtures, tmp_path, capsys):
    project = fixtures / "project"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(project, arcname="lean")
    (tmp_path / "lean.tar.gz.part01").write_bytes(buf.getvalue())
    stem = str(tmp_path / "lean.tar.gz")
    outs = []
    for extra in ([], ["--archive", stem, "--under", "lean"]):
        out = tmp_path / f"scan{len(outs)}.json"
        assert main(["scan", str(project), "--json", str(out), *extra]) == 0
        body = json.loads(out.read_text(encoding="utf-8"))
        outs.append((body["files"], body["lines"], body["hits"]))
    assert outs[0] == outs[1]
    capsys.readouterr()
    assert main(["imports", str(project), "--archive", stem, "--under", "lean"]) == 0
    assert "import cone of Statements, Main: 3 modules" in capsys.readouterr().out
    assert main(["statements", str(project), "--archive", stem, "--under", "lean"]) == 0
    assert "names traced through 7 files" in capsys.readouterr().out
