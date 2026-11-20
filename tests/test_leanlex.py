from zeta_checker.leanlex import Lines, ident_after, ident_before, mask


def kept(src: str) -> str:
    text = mask(src).text
    assert len(text) == len(src)
    assert [i for i, c in enumerate(text) if c == "\n"] == [
        i for i, c in enumerate(src) if c == "\n"
    ]
    return " ".join(text.split())


def test_line_comment():
    assert kept("theorem t := rfl -- sorry\nnext") == "theorem t := rfl next"


def test_nested_block_comment():
    assert kept("a /- x /- y -/ sorry -/ b") == "a b"
    assert kept("/-- doc -/ c /-! mod -/ d") == "c d"
    assert kept("/--/ e") == "e"


def test_strings():
    assert kept('x := "sorry" ; y') == 'x := " " ; y'
    assert kept('x := "a \\" sorry" y') == 'x := " " y'
    assert kept('x := "--" sorry') == 'x := " " sorry'
    assert kept('x := "/-" sorry -/') == 'x := " " sorry -/'


def test_raw_strings():
    assert kept('r#"a "b" sorry"# z') == 'r#" "# z'
    assert kept('r"no escape \\" y') == 'r" " y'
    assert kept('bar"s" t') == 'bar" " t'


def test_char_literals_and_primes():
    assert kept("c := '\"' sorry") == "c := ' ' sorry"
    assert kept("c := '\\'' x") == "c := ' ' x"
    assert kept("f' x' y''") == "f' x' y''"


def test_interpolation_keeps_code():
    assert kept('s!"val {f "in"} more"') == 's!" {f " "} "'
    assert kept('m!"a {x} b {sorry}"') == 'm!" {x} {sorry}"'
    assert kept('s!"{ {a} }"') == 's!"{ {a} }"'


def test_guillemets_hide_comment_starts():
    assert kept("def «a--b» := «c/-d» x") == "def «a--b» := «c/-d» x"


def test_unterminated_flags():
    assert mask("x /- never closed").flags == [(2, "unterminated comment")]
    assert mask('x "open').flags == [(2, "unterminated string")]


def test_identifier_bounds():
    text = "exact Lean.Meta.mkSorry ty"
    p = text.index("mkSorry")
    assert text[ident_before(text, p) : p] == "Lean.Meta."
    src = "IO.Process.spawn x"
    assert src[: ident_after(src, 2)] == "IO.Process.spawn"


def test_lines():
    lines = Lines("a\nbb\n\nccc")
    assert [lines.line(i) for i in (0, 2, 3, 5, 6, 9)] == [1, 2, 2, 3, 4, 4]
    assert lines.text(2) == "bb" and lines.text(4) == "ccc"
