import importlib
import json
import sys
import types


def _install_starlette_1_stubs(monkeypatch):
    starlette = types.ModuleType("starlette")
    applications = types.ModuleType("starlette.applications")
    routing = types.ModuleType("starlette.routing")
    templating = types.ModuleType("starlette.templating")
    responses = types.ModuleType("starlette.responses")

    class Starlette:
        def __init__(
            self,
            debug=False,
            routes=None,
            middleware=None,
            exception_handlers=None,
            lifespan=None,
            **kwargs,
        ):
            if kwargs:
                unexpected = next(iter(kwargs))
                raise TypeError(
                    f"Starlette.__init__() got an unexpected keyword argument '{unexpected}'"
                )
            self.debug = debug
            self.routes = routes
            self.middleware = middleware
            self.exception_handlers = exception_handlers
            self.lifespan = lifespan

    class Route:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Jinja2Templates:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _Response:
        def __init__(self, content=None, status_code=200):
            self.status_code = status_code
            if isinstance(content, (dict, list)):
                self.body = json.dumps(content).encode("utf-8")
            elif isinstance(content, bytes):
                self.body = content
            else:
                self.body = str(content or "").encode("utf-8")

    class JSONResponse(_Response):
        pass

    class PlainTextResponse(_Response):
        pass

    setattr(applications, "Starlette", Starlette)
    setattr(routing, "Route", Route)
    setattr(templating, "Jinja2Templates", Jinja2Templates)
    setattr(responses, "JSONResponse", JSONResponse)
    setattr(responses, "PlainTextResponse", PlainTextResponse)

    monkeypatch.setitem(sys.modules, "starlette", starlette)
    monkeypatch.setitem(sys.modules, "starlette.applications", applications)
    monkeypatch.setitem(sys.modules, "starlette.routing", routing)
    monkeypatch.setitem(sys.modules, "starlette.templating", templating)
    monkeypatch.setitem(sys.modules, "starlette.responses", responses)

    sse_starlette = types.ModuleType("sse_starlette")
    sse_module = types.ModuleType("sse_starlette.sse")

    class EventSourceResponse:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    setattr(sse_module, "EventSourceResponse", EventSourceResponse)
    monkeypatch.setitem(sys.modules, "sse_starlette", sse_starlette)
    monkeypatch.setitem(sys.modules, "sse_starlette.sse", sse_module)


def test_app_imports_with_starlette_1_lifespan_api(monkeypatch):
    previous_app = sys.modules.pop("app", None)
    _install_starlette_1_stubs(monkeypatch)

    try:
        dashboard_app = importlib.import_module("app")
        assert dashboard_app.app.lifespan is dashboard_app._dashboard_lifespan
    finally:
        sys.modules.pop("app", None)
        if previous_app is not None:
            sys.modules["app"] = previous_app
