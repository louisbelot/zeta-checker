import json
import re
from pathlib import Path

import pytest

from zeta_checker import forms, statements

CHALLENGES = Path(__file__).parent.parent / "challenges"


def lean_defs():
    out = {}
    for path in sorted((CHALLENGES / "ZetaForms").glob("*.lean")):
        rel = path.relative_to(CHALLENGES).as_posix()
        for d in statements.parse(path.read_text(encoding="utf-8"), rel).decls:
            out[d.full] = (rel, d.body)
    return out


@pytest.mark.parametrize("form", forms.FORMS, ids=lambda f: f.name)
def test_form_text_matches_lean_file(form):
    rel, body = lean_defs()[form.name]
    assert rel == form.file
    assert statements.squash(body) == statements.squash(form.statement)


def test_every_form_has_a_challenge_and_config():
    stated = {}
    for path in (CHALLENGES / "Challenges").glob("*.lean"):
        m = re.search(r"^theorem (\w+) : (\S+) := sorry$", path.read_text(encoding="utf-8"), re.M)
        config = json.loads((CHALLENGES / "comparator" / f"{path.stem}.json").read_text())
        assert config["challenge_module"] == f"Challenges.{path.stem}"
        assert config["theorem_names"] == [m.group(1)]
        stated[m.group(2)] = path.stem
    assert set(stated) == {f.name for f in forms.FORMS} | {"RiemannHypothesis"}


def test_primitive_grh_beats_plain_grh():
    found = ["DirichletCharacter", ".IsPrimitive", ".LFunction"]
    form, exact = forms.lookup("x", "x", found)
    assert form.name == "ZetaForms.GRHPrimitive" and not exact
    assert forms.lookup("x", "x", ["ℕ"]) == (None, False)
