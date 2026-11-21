import random
import xml.etree.ElementTree as ET

from zeta_checker import declgraph

CORE = b"""import Mathlib

namespace Alg

def base : Nat := 0

structure Pack where
  val : Nat

theorem step : base = 0 := rfl

theorem uses_field (p : Pack) : p.val = Pack.val p := rfl

instance : Inhabited Pack := \xe2\x9f\xa8\xe2\x9f\xa8base\xe2\x9f\xa9\xe2\x9f\xa9

end Alg

theorem Alg.Pack.lift : Alg.step = Alg.step := rfl
"""

TOP = b"""import Core

open Alg

-- unused_by_comment
theorem main : base = 0 := step

theorem other : True := by
  have := Pack.lift
  exact trivial

def unused : Nat := 1

def change : Nat := 2

theorem shadow (base : Nat) : base = base := by
  change base = base
  rfl
"""


def pairs():
    return [("Core.lean", CORE), ("Top.lean", TOP)]


def graph():
    return declgraph.build(pairs)


def test_names_and_kinds():
    g = graph()
    assert g.names[:4] == ["Alg.base", "Alg.Pack", "Alg.step", "Alg.uses_field"]
    assert g.names[4] == "Alg.<instance Core.lean:14>"
    assert g.kinds.count("theorem") == 6 and g.repeated == 0
    assert g.where(g.index["main"]) == "Top.lean:6"


def test_sizes_span_to_next_decl():
    g = graph()
    assert g.sizes[g.index["Alg.base"]] == 2
    assert g.sizes[g.index["unused"]] == 2
    assert g.sizes[g.index["shadow"]] == 3


def test_resolution():
    g = graph()
    out = {g.names[v]: sorted(g.names[w] for w in g.out(v)) for v in range(len(g))}
    assert out["Alg.step"] == ["Alg.base"]
    assert out["Alg.uses_field"] == ["Alg.Pack"]
    assert out["Alg.<instance Core.lean:14>"] == ["Alg.Pack", "Alg.base"]
    assert out["Alg.Pack.lift"] == ["Alg.step"]
    assert out["main"] == ["Alg.base", "Alg.step"]
    assert out["other"] == ["Alg.Pack.lift"]
    assert out["unused"] == [] and out["shadow"] == []


def test_resolve_order():
    index = {"A.B.x": 0, "A.x": 1, "x": 2, "O.y": 3, "P.y": 4, "T": 5}
    scopes = declgraph._scopes("A.B")
    assert declgraph.resolve("x", scopes, [], index) == [0]
    assert declgraph.resolve("x", declgraph._scopes("A"), [], index) == [1]
    assert declgraph.resolve("_root_.x", scopes, [], index) == [2]
    assert declgraph.resolve("y", scopes, ["O", "P"], index) == [3, 4]
    assert declgraph.resolve("T.mk.foo", scopes, [], index) == [5]
    assert declgraph.resolve("h.trans", scopes, [], index) == []


def test_local_names():
    got = declgraph.local_names("fun x ⟨a, b⟩ => foo x\nobtain ⟨y, hy⟩ := lem z\n∀ k ∈ S, P k")
    assert got == {"x", "a", "b", "y", "hy", "k"}
    got = declgraph.local_names("rcases lem z with ⟨c, hc⟩\nchoose f hf using bar")
    assert got == {"c", "hc", "f", "hf"}
    assert declgraph.local_names("(p q : Pack) [inst : Foo] {n : ℕ}") == {"p", "q", "inst", "n"}


def test_open_names():
    opens = ["Real Complex", "scoped BigOperators", "Foo in", "Bar (baz qux)", "Nat hiding add"]
    assert declgraph.open_names(opens) == ["Real", "Complex", "Foo", "Bar", "Nat"]


def test_reach_and_tree():
    g = graph()
    roots = [g.index["main"], g.index["other"]]
    t = declgraph.dominator_tree(g, roots)
    reached = {g.names[v] for v in t.idom}
    assert reached == {"main", "other", "Alg.base", "Alg.step", "Alg.Pack.lift"}
    assert g.names[t.idom[g.index["Alg.Pack.lift"]]] == "other"
    assert t.idom[g.index["Alg.step"]] == -1
    assert t.count[-1] == 5
    assert t.lines[-1] == sum(g.sizes[g.index[n]] for n in reached)
    rows = declgraph.spine(t, 1, 2)
    assert [(d, g.names[v]) for d, v in rows][:2] == [(0, "other"), (1, "Alg.Pack.lift")]


def brute_dominators(succ, n, root):
    def reachable(skip):
        seen, stack = {root}, [root]
        while stack:
            v = stack.pop()
            for w in succ[v]:
                if w != skip and w not in seen:
                    seen.add(w)
                    stack.append(w)
        return seen

    full = reachable(-1)
    dom = {v: {d for d in full if d in (v, root) or v not in reachable(d)} for v in full}
    idom = {}
    for v in full - {root}:
        strict = dom[v] - {v}
        idom[v] = next(d for d in strict if all(e in dom[d] for e in strict))
    return idom


def test_dominators_match_brute_force():
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(2, 12)
        succ = [rng.sample(range(n), rng.randint(0, min(3, n))) for _ in range(n)]
        got = declgraph.dominators(lambda v, s=succ: s[v], n, 0)
        want = brute_dominators(succ, n, 0)
        assert {v: got[v] for v in want} == want
        assert all(got[v] == -1 for v in range(1, n) if v not in want)


def test_dominators_irreducible_loop():
    succ = {5: [4, 3], 4: [1], 3: [2], 1: [2], 2: [1]}
    nodes = sorted(succ)
    ix = {v: i for i, v in enumerate(nodes)}
    lists = [[ix[w] for w in succ[v]] for v in nodes]
    idom = declgraph.dominators(lambda i: lists[i], len(nodes), ix[5])
    assert {nodes[i]: nodes[idom[i]] for i in range(len(nodes))} == {
        1: 5,
        2: 5,
        3: 5,
        4: 5,
        5: 5,
    }


def test_svg_is_xml_and_escaped():
    rows = [(0, "main", 120, "(3 decls)"), (1, "Alg.<instance x>", 40, "(1 decls)")]
    doc = declgraph.svg(rows, "tree & co")
    root = ET.fromstring(doc)
    texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
    assert "tree & co" in texts and "Alg.<instance x>" in texts
    assert "120 (3 decls)" in texts
