import shutil

import pytest

from zeta_checker import lake

MATHLIB = "0df444a360eaa60ab8c11dca51a86af692955474"


@pytest.fixture
def project(fixtures, tmp_path):
    dest = tmp_path / "project"
    shutil.copytree(fixtures / "project", dest)
    return dest


def test_load_and_pins(project):
    lk = lake.load(project)
    assert lk.toolchain == "leanprover/lean4:v4.33.1" and lk.notes == []
    assert lake.pins(lk) == [
        {
            "name": "mathlib",
            "source": "https://github.com/leanprover-community/mathlib4",
            "lakefile": MATHLIB,
            "manifest": MATHLIB,
            "match": True,
        }
    ]
    names = [p["name"] for p in lake.packages(lk)]
    assert names == ["mathlib", "batteries"]


def test_pin_mismatch_and_unofficial_toolchain(project):
    (project / "lean-toolchain").write_text("someone/lean4:custom\n")
    text = (project / "lake-manifest.json").read_text()
    (project / "lake-manifest.json").write_text(text.replace(MATHLIB, "f" * 40, 1))
    lk = lake.load(project)
    assert "not an official" in lk.notes[0]
    assert lake.pins(lk)[0]["match"] is False


def test_lakefile_lean_is_noted(project):
    (project / "lakefile.lean").write_text("import Lake\nopen Lake DSL\n")
    assert any("runs when it loads" in n or "Lake runs" in n for n in lake.load(project).notes)


def test_arguments_and_native_keys(project):
    lk = lake.load(project)
    rows = lake.arguments(lk)
    assert "moreLeanArgs = ['--tstack=400000']" in rows
    assert any(r.startswith("lean_lib Extra: leanOptions") for r in rows)
    assert lake.native(lk) == []
    lk.config["lean_lib"][0]["precompileModules"] = True
    assert lake.native(lk) == ["lean_lib.0.precompileModules = True"]


def test_globs():
    assert lake.glob_match("Foo.+", "Foo.Bar") and not lake.glob_match("Foo.+", "Foo")
    assert lake.glob_match("Foo.*", "Foo") and lake.glob_match("Foo.*", "Foo.Bar.Baz")
    assert not lake.glob_match("Foo.*", "FooBar")
    assert lake.glob_match("Main", "Main") and not lake.glob_match("Main", "Main.X")


def test_coverage(project):
    cov = lake.coverage(lake.load(project))
    assert cov["modules"] == 7
    assert cov["per_lib"] == {"Proof": 2, "Extra": 2, "Main": 2}
    assert cov["unmatched"] == ["Stray.Orphan"]
    assert cov["not_default"] == ["Extra"]
    assert cov["multiple"] == 0


def test_stray_files(project):
    (project / "bin").mkdir()
    (project / "bin/tool").write_bytes(b"\x7fELF\x02\x01\x01\x00")
    (project / "notes.txt").write_text("hi")
    assert lake.stray_files(project) == [("bin/tool", "elf"), ("notes.txt", "other")]


def test_options_from_lean_options_and_arguments(fixtures, tmp_path):
    lk = lake.load(fixtures / "project")
    assert ("package", "autoImplicit", "False") in lake.options(lk)
    assert ("lean_lib Extra", "synthInstance.maxHeartbeats", "400000") in lake.options(lk)
    (tmp_path / "lakefile.toml").write_text(
        'name = "x"\nmoreLeanArgs = ["-Ddebug.skipKernelTC=true", "--tstack=1"]\n', encoding="utf-8"
    )
    assert lake.options(lake.load(tmp_path)) == [("package", "debug.skipKernelTC", "true")]


def test_roots_skip_glob_libs(fixtures):
    assert lake.roots(lake.load(fixtures / "project")) == ["Statements", "Main"]
