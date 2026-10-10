"""T022: acceptance criteria extraction (FR-002, FR-002a, FR-003).

The two jobs this module does must not be conflated: `source_text` is verbatim,
for display and traceability; `normalized` exists only for comparison. Several
tests below exist purely to pin that distinction.
"""

import pytest

from jira_testgen.criteria import CriteriaNotFound, extract_criteria

DESCRIPTION_WITH_HEADING = """\
Users who forget their password need a way back in.

### Acceptance Criteria

- User can request a reset link with a registered email address.
- Reset link expires after 24 hours.
- An unregistered address shows no hint that it is unregistered.

### Notes

Out of scope: SSO accounts.
"""

DESCRIPTION_BOLD_LABEL = """\
Some preamble.

**Acceptance criteria**

- First criterion.
- Second criterion.
"""

DESCRIPTION_PROSE = """\
## Acceptance Criteria

The user can request a reset link.
The link must expire after 24 hours.
"""

DESCRIPTION_NUMBERED = """\
### Acceptance Criteria

1. User can request a reset link.
2. Reset link expires after 24 hours.
"""

DESCRIPTION_NO_SECTION = """\
Users who forget their password need a way back in.
No criteria were written down for this story.
"""


def test_criteria_are_read_from_a_labelled_description_section():
    result = extract_criteria(description_text=DESCRIPTION_WITH_HEADING)
    assert result.source == "description"
    assert [c.label for c in result.criteria] == ["AC-1", "AC-2", "AC-3"]


def test_source_text_is_kept_verbatim():
    # FR-003: what a human reads must be exactly what Jira holds.
    result = extract_criteria(description_text=DESCRIPTION_WITH_HEADING)
    assert (
        result.criteria[0].source_text
        == "User can request a reset link with a registered email address."
    )


def test_extraction_stops_at_the_next_heading():
    # "Out of scope: SSO accounts." lives under Notes and is not a criterion.
    result = extract_criteria(description_text=DESCRIPTION_WITH_HEADING)
    assert len(result.criteria) == 3
    assert all("SSO" not in c.source_text for c in result.criteria)


def test_a_bolded_label_is_recognised_as_a_section():
    result = extract_criteria(description_text=DESCRIPTION_BOLD_LABEL)
    assert len(result.criteria) == 2


def test_prose_criteria_are_split_per_line():
    # Teams that write criteria as sentences rather than lists still work.
    result = extract_criteria(description_text=DESCRIPTION_PROSE)
    assert len(result.criteria) == 2
    assert result.criteria[1].source_text == "The link must expire after 24 hours."


def test_numbering_prefixes_are_stripped_from_source_text():
    result = extract_criteria(description_text=DESCRIPTION_NUMBERED)
    assert result.criteria[0].source_text == "User can request a reset link."


def test_configured_field_wins_over_the_description():
    # FR-002 resolution order: the field when the setting is present.
    result = extract_criteria(
        description_text=DESCRIPTION_WITH_HEADING,
        ac_field_text="- Only criterion from the field.",
    )
    assert result.source == "field"
    assert len(result.criteria) == 1
    assert result.criteria[0].source_text == "Only criterion from the field."


def test_empty_configured_field_falls_back_to_the_description():
    # An empty field is "no criteria from that source", not a stop.
    result = extract_criteria(description_text=DESCRIPTION_WITH_HEADING, ac_field_text="   ")
    assert result.source == "description"
    assert len(result.criteria) == 3


def test_field_without_list_markers_is_still_parsed():
    result = extract_criteria(
        description_text="", ac_field_text="First thing.\nSecond thing."
    )
    assert [c.source_text for c in result.criteria] == ["First thing.", "Second thing."]


def test_no_criteria_anywhere_raises_and_names_both_places():
    # FR-005: a stop, not a degraded run, and the message must say where it looked.
    with pytest.raises(CriteriaNotFound) as excinfo:
        extract_criteria(description_text=DESCRIPTION_NO_SECTION, ac_field="customfield_10040")
    message = str(excinfo.value)
    assert "customfield_10040" in message
    assert "Acceptance Criteria" in message


def test_no_criteria_message_says_the_field_was_unset_when_it_was():
    with pytest.raises(CriteriaNotFound) as excinfo:
        extract_criteria(description_text=DESCRIPTION_NO_SECTION)
    assert "JIRA_AC_FIELD" in str(excinfo.value)


def test_labels_are_sequential_and_ordinals_match():
    result = extract_criteria(description_text=DESCRIPTION_WITH_HEADING)
    for index, criterion in enumerate(result.criteria, start=1):
        assert criterion.label == f"AC-{index}"
        assert criterion.ordinal == index


def test_blank_and_marker_only_lines_are_ignored():
    text = "### Acceptance Criteria\n\n-\n\n- Real criterion.\n\n   \n"
    result = extract_criteria(description_text=text)
    assert [c.source_text for c in result.criteria] == ["Real criterion."]
