from zeta_checker import manuscript

TEXT = """--- page 1 ---
                         Chapter 1. Setup
     Definition 1.1.1.1. A gadget is a pair.
     Lemma 1.1.1.2 (Gadgets (and pairs) exist). Every set has a gadget.
Proof. By Definition 1.1.1.1 and [Ab, Thm.2.3]. The bound (1.1.1.3) holds.
(1.1.1.3)                 x <= y
     Theorem 1.1.1.5 (Main bound). Gadgets are small.
--- page 2 ---
Proof. Combine Lemma 1.1.1.2 with Lemma 1.1.1.2 and Theorem ??; see [Ab; Cd, §4].
Theorem 1.1.1.5 has no analog here. Lemma 1.1.1.2(3) gives the rest.
Theorem 1.1.1.5.
Lemma 1.1.1.2. Restated at the margin.
The details are left to the reader, and Proposition 1.1.1.9 is missing.
TODO fix the constant.
2Insert statement.
--- page 3 ---
                              Bibliography
[Ab] A. Author. A book on gadgets.
  Second line of the entry.
[Cd] C. Dee. Pairs.
[Ef] E. Ef. Never cited.
"""

OUTLINE = "Chapter 1. Setup  ..  1\n  1.1. Gadgets  ..  1\nBibliography  ..  3\n"


def tri():
    return manuscript.triage(TEXT, OUTLINE)


def test_headers():
    found = tri().results
    got = [(r.label, r.title, r.page, r.line) for r in found]
    assert got == [
        ("Definition 1.1.1.1", "", 1, 2),
        ("Lemma 1.1.1.2", "Gadgets (and pairs) exist", 1, 3),
        ("Theorem 1.1.1.5", "Main bound", 1, 6),
        ("Lemma 1.1.1.2", "", 2, 4),
    ]


def test_cross_refs_skip_brackets_and_headers():
    tr = tri()
    assert tr.edges == {("1.1.1.2", "1.1.1.1"): 1, ("1.1.1.5", "1.1.1.2"): 3}
    assert tr.dangling == {"Proposition 1.1.1.9": 1}
    assert tr.indegree() == {"1.1.1.1": 1, "1.1.1.2": 1}


def test_duplicates_and_gaps():
    tr = tri()
    assert list(tr.duplicates) == ["1.1.1.2"]
    assert tr.gaps == {"1.1.1": [("1.1.1.3", "equation"), ("1.1.1.4", "")]}


def test_markers():
    kinds = [(k, page, line) for k, page, line, _ in tri().markers]
    assert kinds == [
        ("editorial", 2, 1),
        ("omitted", 2, 5),
        ("editorial", 2, 6),
        ("note", 2, 7),
    ]


def test_bibliography_and_citations():
    tr = tri()
    assert tr.bibliography["Ab"] == "A. Author. A book on gadgets. Second line of the entry."
    assert set(tr.bibliography) == {"Ab", "Cd", "Ef"}
    assert tr.citations == {"Ab": [1, 2], "Cd": [2]}


def test_chapters_from_outline():
    assert tri().chapters == [("Chapter 1. Setup", 1, 2), ("Bibliography", 3, 1)]
    assert manuscript.outline(OUTLINE)[1] == (1, "1.1. Gadgets", 1)
