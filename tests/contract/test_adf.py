"""T014: ADF contract tests.

NOTE ON FIDELITY: T014 asks for *recorded real* Jira payloads. The fixtures
below are built to Atlassian's documented ADF node shapes, not captured from a
live site, because this environment has no Jira credentials. They are therefore
a faithful reading of the published schema rather than evidence of what one
site actually returns. Before relying on this layer, capture a real
``GET /rest/api/3/issue/{key}?fields=description`` response from the target site
and add it here -- the shapes most worth confirming are tables, nested lists,
and whatever the team's acceptance-criteria field returns.
"""

from jira_testgen.jira import adf

# A story description of the shape this tool is built to read: a heading, a
# paragraph, and an acceptance-criteria section as a bullet list.
STORY_DESCRIPTION = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Users who forget their password need a way back in."}
            ],
        },
        {
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Acceptance Criteria"}],
        },
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "User can request a reset link with a registered email address.",
                                }
                            ],
                        }
                    ],
                },
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Reset link expires after 24 hours."}
                            ],
                        }
                    ],
                },
            ],
        },
    ],
}

DESCRIPTION_WITH_IMAGE = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "See the mockup below."}]},
        {
            "type": "mediaSingle",
            "attrs": {"layout": "center"},
            "content": [
                {"type": "media", "attrs": {"id": "abc-123", "type": "file", "collection": "x"}}
            ],
        },
    ],
}

DESCRIPTION_WITH_MARKS = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Reset link expires after "},
                {"type": "text", "text": "24 hours", "marks": [{"type": "strong"}]},
                {"type": "text", "text": "."},
            ],
        }
    ],
}


def test_extract_text_keeps_heading_markers_so_sections_stay_detectable():
    result = adf.extract_text(STORY_DESCRIPTION)
    assert "### Acceptance Criteria" in result.text


def test_extract_text_keeps_list_items_as_markers():
    result = adf.extract_text(STORY_DESCRIPTION)
    assert "- User can request a reset link with a registered email address." in result.text
    assert "- Reset link expires after 24 hours." in result.text


def test_extract_text_reports_no_non_text_content_for_a_plain_story():
    assert adf.extract_text(STORY_DESCRIPTION).had_non_text is False


def test_extract_text_flags_an_image_rather_than_dropping_it_silently():
    result = adf.extract_text(DESCRIPTION_WITH_IMAGE)
    assert result.had_non_text is True
    assert "See the mockup below." in result.text


def test_marked_text_is_joined_without_losing_words():
    # Bold or italic runs arrive as separate text nodes; splitting a sentence
    # across them must not mangle it.
    assert adf.extract_text(DESCRIPTION_WITH_MARKS).text == (
        "Reset link expires after 24 hours."
    )


def test_plain_string_description_is_accepted():
    # Some configurations and the v2 API return a bare string.
    assert adf.extract_text("Just text").text == "Just text"


def test_none_description_is_empty_not_an_error():
    result = adf.extract_text(None)
    assert result.text == ""
    assert result.had_non_text is False


def test_builder_emits_a_valid_document_envelope():
    document = adf.doc(adf.heading("Steps"), adf.ordered_list(["Open the page.", "Sign in."]))
    assert document["type"] == "doc"
    assert document["version"] == 1
    assert document["content"][0]["type"] == "heading"
    assert document["content"][1]["type"] == "orderedList"


def test_built_document_round_trips_back_to_its_text():
    document = adf.doc(
        adf.heading("Preconditions"),
        adf.paragraph("A user account exists."),
        adf.heading("Steps"),
        adf.ordered_list(["Open the reset page.", "Enter the email address."]),
    )
    text = adf.extract_text(document).text
    assert "Preconditions" in text
    assert "A user account exists." in text
    assert "- Open the reset page." in text
    assert "- Enter the email address." in text


def test_paragraph_splits_multiline_text_into_hard_breaks():
    built = adf.paragraph("line one\nline two")
    types = [node["type"] for node in built["content"]]
    assert "hardBreak" in types


def test_empty_paragraph_is_still_structurally_valid():
    built = adf.paragraph("")
    assert built["type"] == "paragraph"
    assert built["content"]
