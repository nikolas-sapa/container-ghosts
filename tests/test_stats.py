import pytest

from ghosts.stats import (
    clopper_pearson, discordance, exact_mcnemar, exact_repeat_noise_comparison,
    holm_adjust, newcombe_wilson,
)


def test_exact_mcnemar_known_one_sided_example():
    assert exact_mcnemar(9, 1, "greater") == pytest.approx(11 / 1024)
    assert exact_mcnemar(9, 1, "less") == pytest.approx(1023 / 1024)


def test_exact_mcnemar_no_discordance_is_not_evidence():
    assert exact_mcnemar(0, 0, "greater") == 1.0


def test_discordance_table():
    result = discordance([1, 1, 0, 0], [0, 1, 1, 0])
    assert result["n10"] == 1
    assert result["n01"] == 1
    assert result["n11"] == 1
    assert result["n00"] == 1
    assert result["delta"] == 0


def test_clopper_pearson_known_intervals():
    assert clopper_pearson(5, 10) == pytest.approx((0.18708602844739855, 0.8129139715526015))
    assert clopper_pearson(0, 10) == pytest.approx((0.0, 0.3084971078187608))


def test_newcombe_wilson_known_interval():
    assert newcombe_wilson(5, 10) == pytest.approx((0.236593090512564, 0.7634069094874361))


def test_holm_known_ordering():
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_noise_comparison_reports_repeat_interval():
    result = exact_repeat_noise_comparison([1, 1, 0, 0], [0, 0, 1, 0])
    assert result["n10"] == 2
    assert result["n01"] == 1
    assert result["exact_repeat_rate"] == 0.25
    assert len(result["exact_repeat_rate_clopper_pearson"]) == 2


def test_strict_scoring_parser_and_canary():
    from ghosts.score import canary_leaks, parse_three_letters, semantic_answers
    assert parse_three_letters(" A,B,A \n") == ("A", "B", "A")
    assert parse_three_letters("A,B,A.") is None
    mapping = {"q1": {"A": "red", "B": "blue"}, "q2": {"A": "right", "B": "wrong"}, "q3": {"A": "camera photograph", "B": "AI-generated image"}}
    assert semantic_answers("A,B,B", mapping)["q3"] == "AI-generated image"
    assert canary_leaks("prefix GHOSTCANARY_X suffix", "GHOSTCANARY_X") is True
