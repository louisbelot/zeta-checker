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
    assert "imports: Mathlib" in text and "project imports: none" in text
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
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"sources": []}', encoding="utf-8")
    cmd = ["-w", str(tmp_path), "extract", "--manifest", str(manifest)]
    assert main(cmd + ["--list", "--record"]) == 0
    text = capsys.readouterr().out
    assert "1 members: 1 files" in text and "(recorded)" in text
    record = json.loads(manifest.read_text(encoding="utf-8"))["joined"]["lean.tar.gz"]
    assert record["parts"] == 1 and record["size"] == len(buf.getvalue())
    assert main(cmd) == 0
    assert "(matches the manifest)" in capsys.readouterr().out
    assert (tmp_path / "alpoge_lean/lean/src/A.lean").read_bytes() == b"x\ny\n\n"
    record["sha256"] = "0" * 64
    manifest.write_text(json.dumps({"joined": {"lean.tar.gz": record}}), encoding="utf-8")
    assert main(cmd + ["--list"]) == 1
    assert "differs from the manifest" in capsys.readouterr().out


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
    assert main(["decls", str(project), "--archive", stem, "--under", "lean"]) == 0
    assert "reached by name from the roots: 7 declarations" in capsys.readouterr().out


def test_decls_command(fixtures, tmp_path, capsys):
    out, svg = tmp_path / "decls.json", tmp_path / "decls.svg"
    args = ["decls", str(fixtures / "project"), "--json", str(out), "--svg", str(svg)]
    assert main(args) == 0
    text = capsys.readouterr().out
    assert "11 declarations in 7 files" in text
    assert "primitive  [2 decls, 7 lines]  src/Main.lean:8" in text
    assert "  Proof.grh  [1 decls, 6 lines]  src/Proof/Core.lean:7" in text
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["reached"] == 7 and body["folders"]["src/Extra.lean"] == [1, 0]
    assert svg.read_text(encoding="utf-8").startswith("<svg")


def test_manuscript_command(tmp_path, capsys):
    text = tmp_path / "paper.txt"
    text.write_text(
        "--- page 1 ---\n     Lemma 2.1.1.1. Easy.\n     Theorem 2.1.1.2. By Lemma 2.1.1.1 "
        "and Lemma 2.1.1.7.\n--- page 2 ---\nAs in Theorem ??.\n",
        encoding="utf-8",
    )
    (tmp_path / "paper.outline.txt").write_text("Chapter 2  ..  1\n", encoding="utf-8")
    out = tmp_path / "paper.json"
    assert main(["manuscript", str(text), "--index", "--json", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "numbered results: 2" in printed and "  p1  Theorem 2.1.1.2" in printed
    assert "Lemma 2.1.1.7  x1" in printed
    assert "p2:1 [editorial] As in Theorem ??." in printed
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["edges"] == [["2.1.1.2", "2.1.1.1", 1]]
    assert body["chapters"] == [["Chapter 2", 1, 2]]


def test_criteria_command(capsys):
    assert main(["criteria", "--robin", "6000", "--li", "3", "--baez-duarte", "2"]) == 0
    text = capsys.readouterr().out
    assert "27 exceptions, largest 5040" in text
    assert "\n1  0.023095708966" in text and "\n2  0.289964574" in text


def test_li_command(tmp_path, capsys):
    out = tmp_path / "li.json"
    assert main(["li", "--n", "3", "--zeros", "20", "--certify", "--json", str(out)]) == 0
    assert "lambda_1..lambda_3 certified positive: True" in capsys.readouterr().out
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body[0]["certified"][0].startswith("0.02309570896612103")
    assert body[2]["zeros"]["zeros"] == 20


def test_forms_command(capsys):
    assert main(["forms"]) == 0
    assert "ZetaForms.Robin" in capsys.readouterr().out


def test_colossal_command(tmp_path, capsys):
    png = tmp_path / "robin.png"
    assert main(["colossal", "--limit", "1e5", "--chart", str(png)]) == 0
    text = capsys.readouterr().out
    assert "lowest (e^g loglog N - sigma(N)/N) sqrt(log N) = 0.235680 at log N = 10.9231" in text
    assert png.stat().st_size > 10_000
