from llm.gemini_client import _gemini_schema


def test_nullable_json_schema_is_converted_for_gemini():
    schema = _gemini_schema(
        {
            "type": "object",
            "properties": {"due_at": {"type": ["string", "null"]}},
        }
    )
    assert schema == {
        "type": "OBJECT",
        "properties": {"due_at": {"type": "STRING"}},
    }
