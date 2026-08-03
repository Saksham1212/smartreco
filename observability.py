"""LangSmith observability helper.

`traceable` decorates agent pipeline functions so the whole reasoning workflow
(analyze -> retrieve -> evaluate -> refine -> generate -> store) is visible as
a single trace in LangSmith. Tracing only activates when LANGCHAIN_TRACING_V2
and LANGCHAIN_API_KEY are set (see config.py); otherwise this is a harmless
passthrough with zero runtime cost, and the app works identically whether or
not the `langsmith` package is even installed.
"""
try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - optional dependency

    def traceable(*_args, **_kwargs):
        if len(_args) == 1 and callable(_args[0]) and not _kwargs:
            return _args[0]

        def _decorator(fn):
            return fn

        return _decorator
