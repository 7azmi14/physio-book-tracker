import pytest

from core.edition import WatchlistEntry
from core.email_digest import (
    EmailError,
    group_titles,
    has_digest_content,
    render_email,
    render_subject,
    render_text,
    send_via_resend,
)
from core.models import BookRecord


def make_record(**kwargs) -> BookRecord:
    kwargs.setdefault("title", "Some Book")
    kwargs.setdefault("source", "crossref")
    return BookRecord(**kwargs)


def make_entry(**kwargs) -> WatchlistEntry:
    kwargs.setdefault("short_title", "Kisner & Colby")
    kwargs.setdefault("title", "Therapeutic Exercise")
    kwargs.setdefault("authors", ["Kisner"])
    kwargs.setdefault("publisher", "F.A. Davis")
    kwargs.setdefault("current_edition", 8)
    return WatchlistEntry(**kwargs)


class FakeConfig:
    site_title = "Physio Book Tracker"
    site_base_url = "https://example.github.io/physio-book-tracker"
    email_recipients = ["alharbi.abd@outlook.com"]
    email_from = "Physio Book Tracker <onboarding@resend.dev>"


def test_has_digest_content_false_when_both_empty():
    assert has_digest_content([], []) is False


def test_has_digest_content_true_with_either():
    assert has_digest_content([(make_record(), make_entry())], []) is True
    assert has_digest_content([], [(make_record(), ["manual therapy"])]) is True


def test_group_titles_groups_by_primary_tag_and_pushes_general_last():
    a = make_record(title="A")
    b = make_record(title="B")
    c = make_record(title="C")
    grouped = group_titles([(a, ["musculoskeletal"]), (b, ["general"]), (c, ["cardiopulmonary rehabilitation"])])
    keys = [k for k, _ in grouped]
    assert keys == ["cardiopulmonary rehabilitation", "musculoskeletal", "general"]


def test_render_subject_combines_counts():
    editions = [(make_record(), make_entry())]
    titles = [(make_record(), ["general"]), (make_record(), ["general"])]
    subject = render_subject(editions, titles)
    assert "1 new edition" in subject
    assert "2 new titles" in subject


def test_render_subject_singular_forms():
    subject = render_subject([(make_record(), make_entry())], [(make_record(), ["general"])])
    assert subject == "Physio Book Tracker: 1 new edition, 1 new title"


def test_render_text_includes_editions_and_grouped_titles():
    record = make_record(title="Orthopedic Physical Assessment", edition=8, url="https://doi.org/x")
    entry = make_entry(short_title="Magee", current_edition=7)
    text = render_text([(record, entry)], [("musculoskeletal", [make_record(title="New MSK Book")])])
    assert "NEW EDITIONS" in text
    assert "Orthopedic Physical Assessment" in text
    assert "Magee, edition 8 (you have 7)" in text
    assert "Musculoskeletal" in text
    assert "New MSK Book" in text


def test_render_email_produces_html_and_text_and_subject():
    record = make_record(title="Frozen Shoulder and Physiotherapy", authors=["Kirupa K"])
    subject, html, text = render_email([], [(record, ["manual therapy"])], FakeConfig())
    assert "1 new title" in subject
    assert "Frozen Shoulder and Physiotherapy" in html
    assert "Manual Therapy" in html  # group heading, title-cased
    assert "Frozen Shoulder and Physiotherapy" in text


def test_send_via_resend_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(EmailError, match="RESEND_API_KEY"):
        send_via_resend("subject", "<p>hi</p>", "hi", FakeConfig(), api_key=None)


def test_send_via_resend_raises_without_recipients():
    class NoRecipients(FakeConfig):
        email_recipients = []

    with pytest.raises(EmailError, match="recipients"):
        send_via_resend("subject", "<p>hi</p>", "hi", NoRecipients(), api_key="fake-key")


def test_send_via_resend_posts_expected_payload():
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return FakeResponse()

    send_via_resend("Subject", "<p>hi</p>", "hi", FakeConfig(), api_key="fake-key", http_post=fake_post)

    assert len(calls) == 1
    url, headers, payload, timeout = calls[0]
    assert url == "https://api.resend.com/emails"
    assert headers["Authorization"] == "Bearer fake-key"
    assert payload["to"] == ["alharbi.abd@outlook.com"]
    assert payload["subject"] == "Subject"


def test_send_via_resend_raises_on_error_status():
    class FakeResponse:
        status_code = 422
        text = "Invalid `from` address"

    def fake_post(url, *, headers, json, timeout):
        return FakeResponse()

    with pytest.raises(EmailError, match="422"):
        send_via_resend("s", "h", "t", FakeConfig(), api_key="fake-key", http_post=fake_post)
