import app as dashboard_app


def test_chat_message_sanitizer_preserves_multimodal_image_content():
    messages = dashboard_app._sanitize_chat_messages([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                {"type": "unsupported", "value": "drop me"},
            ],
        },
        {"role": "assistant", "content": "ok"},
    ])

    assert isinstance(messages[0]["content"], list)
    assert messages[0]["content"] == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert messages[1] == {"role": "assistant", "content": "ok"}


def test_chat_message_sanitizer_keeps_string_messages_and_filters_gateway_errors():
    messages = dashboard_app._sanitize_chat_messages([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Error: Hermes gateway unavailable"},
        {"role": "nonsense", "content": "drop"},
    ])

    assert messages == [{"role": "user", "content": "hello"}]
