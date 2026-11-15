"""SPL XML reading, on an invented document."""

import pytest

from plainpairs import dailymed

SPL = b"""<?xml version="1.0" encoding="UTF-8"?>
<document xmlns="urn:hl7-org:v3">
  <setId root="set-aaaa"/>
  <versionNumber value="7"/>
  <component><structuredBody>
    <component><section>
      <code code="42231-1" codeSystem="2.16.840.1.113883.6.1"/>
      <title>MEDICATION GUIDE</title>
      <text><paragraph>Read this guide first.</paragraph></text>
      <component><section>
        <code code="42229-5"/>
        <title>What is Zorvan?</title>
        <text>
          <paragraph>Zorvan may cause:</paragraph>
          <list><item>headache</item><item>tiredness <content>today</content></item></list>
          <table><tr><td>Headache</td><td>2%</td></tr></table>
        </text>
      </section></component>
    </section></component>
    <component><section>
      <code code="34067-9"/>
      <title>1 INDICATIONS AND USAGE</title>
      <text><paragraph>For testing only.</paragraph></text>
    </section></component>
  </structuredBody></component>
</document>"""


def test_parse_spl_keeps_titles_paragraphs_items_and_counts_tables():
    doc = dailymed.parse_spl(SPL)
    assert (doc["set_id"], doc["version"]) == ("set-aaaa", 7)
    mg = doc["sections"]["medication_guide"]
    assert mg["blocks"] == [
        "MEDICATION GUIDE",
        "Read this guide first.",
        "What is Zorvan?",
        "Zorvan may cause:",
        "headache",
        "tiredness today",
    ]
    assert (mg["titles"], mg["paragraphs"], mg["list_items"], mg["tables"], mg["lists"]) == (
        2,
        2,
        2,
        1,
        1,
    )
    assert doc["sections"]["indications_and_usage"]["blocks"] == [
        "1 INDICATIONS AND USAGE",
        "For testing only.",
    ]


def test_measure_blocks_breaks_at_every_block():
    m = dailymed.measure_blocks(["Zorvan may cause:", "headache", "tiredness"])
    assert m.sentences == 3


def test_a_document_type_declaration_is_refused():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><document xmlns="urn:hl7-org:v3"/>'
    with pytest.raises(Exception):  # noqa: B017 - defusedxml raises its own error types
        dailymed.parse_spl(evil)
