"""Safe notation folding without erasing meaning-bearing financial symbols."""

from canna.retrieval.normalize import normalize


def test_case_width_spacing_and_typographic_separators_share_one_key() -> None:
    assert normalize("Ａ Ｂ＿Ｃ·Ｄ") == normalize("abcd")


def test_decimal_point_is_not_erased() -> None:
    assert normalize("15.4") != normalize("154")


def test_sign_percent_and_slash_remain_meaning_bearing() -> None:
    assert normalize("-1%") != normalize("1")
    assert normalize("a/b") != normalize("ab")
