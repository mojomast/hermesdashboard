import asyncio

import app as dashboard_app


class FakeRequest:
    def __init__(self, session_id, *, headers=None, query_params=None):
        self.path_params = {"session_id": session_id}
        self.headers = headers or {}
        self.query_params = query_params or {}


async def response_events(response):
    iterator = getattr(response, "body_iterator", None)
    if iterator is None:
        args = getattr(response, "args", ())
        iterator = args[0] if args else None
    assert iterator is not None, "EventSourceResponse did not retain its event iterator"
    return [event async for event in iterator]


def stream_events(request):
    response = asyncio.run(dashboard_app.session_stream(request))
    return asyncio.run(response_events(response))


def test_child_stream_assigns_distinct_stable_occurrence_ids_and_resumes_after_header(monkeypatch):
    session_id = "child-resume-header"
    repeated = '{"type":"tool_progress","progress":"same"}'
    state = {
        "events": [
            {"data": repeated},
            {"data": repeated},
            {"data": "[DONE]"},
        ],
        "done": True,
    }
    monkeypatch.setitem(dashboard_app.ACTIVE_CHILD_STREAMS, session_id, state)

    initial = stream_events(FakeRequest(session_id))

    assert [event["data"] for event in initial] == [repeated, repeated, "[DONE]"]
    assert len({event["id"] for event in initial}) == 3
    assert [event["id"].rsplit(":", 1)[1] for event in initial] == ["1", "2", "3"]

    resumed = stream_events(
        FakeRequest(session_id, headers={"last-event-id": initial[0]["id"]})
    )

    assert resumed == initial[1:]
    assert state["events"] == [
        {"data": repeated},
        {"data": repeated},
        {"data": "[DONE]"},
    ]


def test_child_stream_query_resume_and_synthetic_done_are_idempotent(monkeypatch):
    session_id = "child-resume-query"
    state = {
        "events": [{"data": '{"type":"content","content":"hello"}'}],
        "done": True,
    }
    monkeypatch.setitem(dashboard_app.ACTIVE_CHILD_STREAMS, session_id, state)

    initial = stream_events(FakeRequest(session_id))
    assert [event["data"] for event in initial] == [state["events"][0]["data"], "[DONE]"]
    assert initial[1]["id"].endswith(":2")

    after_content = stream_events(
        FakeRequest(session_id, query_params={"lastEventId": initial[0]["id"]})
    )
    assert after_content == [initial[1]]

    after_done = stream_events(
        FakeRequest(session_id, query_params={"last_event_id": initial[1]["id"]})
    )
    assert after_done == []


def test_child_stream_rejects_resume_id_from_a_different_stream(monkeypatch):
    session_id = "child-resume-mismatch"
    state = {"events": [{"data": "one"}, {"data": "[DONE]"}], "done": True}
    monkeypatch.setitem(dashboard_app.ACTIVE_CHILD_STREAMS, session_id, state)

    events = stream_events(
        FakeRequest(session_id, headers={"Last-Event-ID": "different-stream:1"})
    )

    assert [event["data"] for event in events] == ["one", "[DONE]"]
