from core.models import BookRecord
from core.scoring import score_record

INCLUDE = [
    "physiotherapy",
    "physical therapy",
    "rehabilitation",
    "musculoskeletal",
    "manual therapy",
]
EXCLUDE = ["veterinary", "equine", "nursing home administration"]


def make(**kwargs) -> BookRecord:
    kwargs.setdefault("title", "Some Book")
    kwargs.setdefault("source", "test")
    return BookRecord(**kwargs)


def test_title_match_scores_higher_than_description_match():
    title_hit = make(title="Manual Therapy for the Spine")
    desc_hit = make(title="Some Book", description="A text on manual therapy techniques.")
    a = score_record(title_hit, INCLUDE, EXCLUDE)
    b = score_record(desc_hit, INCLUDE, EXCLUDE)
    assert a.score > b.score


def test_no_keyword_match_scores_zero():
    r = make(title="Introduction to Cardiology")
    result = score_record(r, INCLUDE, EXCLUDE)
    assert result.score == 0
    assert result.excluded is False


def test_exclude_keyword_overrides_include_matches():
    r = make(
        title="Equine Rehabilitation and Physical Therapy",
        description="Covers musculoskeletal rehabilitation in horses.",
    )
    result = score_record(r, INCLUDE, EXCLUDE)
    assert result.excluded is True
    assert result.score == 0


def test_multiple_field_matches_accumulate():
    r = make(
        title="Physical Therapy",
        subtitle="A Rehabilitation Approach",
        subjects=["musculoskeletal"],
    )
    result = score_record(r, INCLUDE, EXCLUDE)
    assert result.score > score_record(make(title="Physical Therapy"), INCLUDE, EXCLUDE).score


def test_matched_include_keywords_are_deduplicated():
    r = make(title="Physical Therapy", subtitle="More Physical Therapy Content")
    result = score_record(r, INCLUDE, EXCLUDE)
    assert result.matched_include.count("physical therapy") == 1
