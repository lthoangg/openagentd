"""Tool decorator and Tool class for LLM function-calling.

Parameter descriptions are defined via ``Annotated[type, Field(description=...)]``
directly on the function signature. The docstring describes the tool's use case
for the LLM — no ``Args:`` section required.

Usage::

    from typing import Annotated
    from pydantic import Field
    from app.agent.tools import tool

    @tool
    def search(
        query: Annotated[str, Field(description="The search query string.")],
        max_results: Annotated[int, Field(description="Max results to return.")] = 5,
    ) -> list:
        \"\"\"Search the web for current information and news.\"\"\"
        ...

    @tool(name="custom_name")
    def another_func(
        url: Annotated[str, Field(description="The URL to fetch.")],
    ) -> str:
        \"\"\"Fetch and convert a web page to Markdown.\"\"\"
        ...

Tools are callable (original function behaviour is preserved) and carry
LLM-compatible metadata via ``.name``, ``.description``, and ``.definition``.
"""

from __future__ import annotations

import inspect
from typing import (
    Annotated,
    Any,
    Callable,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from pydantic import BaseModel, ValidationError, create_model

from loguru import logger

from app.agent.errors import ToolArgumentError, ToolExecutionError


class InjectedArg:
    """Marker: annotate a tool parameter with this to hide it from the LLM schema
    and have it injected automatically at call time by the agent.

    The agent passes a ``_injected`` dict to :meth:`Tool.arun`; any parameter
    annotated ``Annotated[T, InjectedArg()]`` receives its value from that dict
    (keyed by the parameter name) and is excluded from the OpenAI tool schema so
    the LLM never sees or fills it.

    Usage::

        async def my_tool(
            query: Annotated[str, Field(description="Search query")],
            _state: Annotated["AgentState | None", InjectedArg()] = None,
        ) -> str:
            # _state is injected by the agent; use it to read messages,
            # session_id, context, etc.
            ...

    The agent calls::

        result = await tool.arun(_injected={"_state": state}, query="...")
    """


def _is_injected(annotation: Any) -> bool:
    """Return True if the annotation contains an InjectedArg marker."""
    if get_origin(annotation) is Annotated:
        for meta in get_args(annotation)[1:]:
            if isinstance(meta, InjectedArg):
                return True
    return False


def _resolve_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline ``$ref`` pointers and drop ``$defs`` from a JSON Schema.

    Pydantic v2's ``model_json_schema()`` emits ``$defs`` + ``$ref`` when a
    parameter uses a nested Pydantic model (e.g. ``list[RememberItem]``).
    Some LLM providers (Gemini, Vertex) reject ``$ref`` outright, so we
    resolve every reference in-place and strip the ``$defs`` block.

    Also strips ``title`` from inlined definitions since providers don't need it.
    """
    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]  # e.g. "#/$defs/RememberItem"
                ref_name = ref_path.rsplit("/", 1)[-1]
                resolved = defs.get(ref_name, node)
                # Deep-copy and recurse (defs can themselves contain $ref)
                resolved = _inline({k: v for k, v in resolved.items()})
                resolved.pop("title", None)
                return resolved
            return {k: _inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_inline(item) for item in node]
        return node

    result = _inline({k: v for k, v in schema.items() if k != "$defs"})
    return result


class Tool:
    """A callable function decorated with LLM function-calling metadata.

    Wraps a plain Python function (sync or async) and exposes:

    * ``.name`` — tool name used in function-calling payloads
    * ``.description`` — use-case description sent to the LLM (from docstring)
    * ``.definition`` — OpenAI-compatible tool definition dict
    * Direct call — ``tool_obj(...)`` delegates to the original function
    * ``await tool_obj.arun(...)`` — validates args with Pydantic, then calls
      the function (supports both sync and async underlying functions)

    Parameter descriptions are sourced from ``Field(description=...)`` inside
    ``Annotated`` type hints on the function signature.
    """

    def __init__(
        self,
        func: Callable,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self._func = func
        # ``Callable`` is the abstract type; only function objects guarantee
        # ``__name__``. Fall back to ``repr`` for callables that don't (e.g.
        # ``functools.partial``) — the explicit *name* kwarg should be used
        # in that case.
        self.name = name or getattr(func, "__name__", repr(func))
        self._custom_description = description

        self._model, self._definition, self._injected_params = self._build()

        # Preserve function metadata so the Tool looks like the original function
        self.__name__ = self.name
        self.__doc__ = func.__doc__
        self.__wrapped__ = func

    # ------------------------------------------------------------------
    # Callable interface — keeps the original function behaviour
    # ------------------------------------------------------------------

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._func(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Tool(name={self.name!r})"

    # ------------------------------------------------------------------
    # LLM-facing metadata
    # ------------------------------------------------------------------

    @property
    def description(self) -> str:
        return self._definition["function"]["description"]

    @property
    def definition(self) -> dict[str, Any]:
        """OpenAI-compatible tool definition dict."""
        return self._definition

    # ------------------------------------------------------------------
    # Validated execution (used by Agent)
    # ------------------------------------------------------------------

    async def arun(self, _injected: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Execute the tool with Pydantic validation.

        Args:
            _injected: Optional dict of runtime-injected values for parameters
                annotated with :class:`InjectedArg`.  These are merged into the
                call after validation and are never exposed to the LLM.  The
                standard key is ``"_state"`` (an :class:`~app.core.state.AgentState`
                instance).
            **kwargs: LLM-provided arguments (validated against the schema).

        Raises:
            :exc:`~app.core.errors.ToolArgumentError`: When Pydantic validation
                of LLM-provided arguments fails.
            :exc:`~app.core.errors.ToolExecutionError`: When the underlying tool
                function raises any other exception.

        Supports both synchronous and asynchronous underlying functions.
        """
        logger.debug("tool_arun tool={} kwargs={}", self.name, list(kwargs.keys()))
        # Strip injected param names that might accidentally appear in kwargs
        llm_kwargs = {k: v for k, v in kwargs.items() if k not in self._injected_params}
        try:
            validated_model = self._model(**llm_kwargs)
        except ValidationError as exc:
            raise ToolArgumentError(
                f"Invalid arguments for tool '{self.name}': {exc}"
            ) from exc
        # Build kwargs from model attributes — preserves nested Pydantic model
        # instances (e.g. list[RememberItem]) instead of collapsing them to dicts
        # as model_dump() would do.
        validated: dict[str, Any] = {
            field: getattr(validated_model, field)
            for field in validated_model.model_fields
        }
        # Merge injected values (not validated — they come from trusted internal code)
        if _injected and self._injected_params:
            for pname in self._injected_params:
                if pname in _injected:
                    validated[pname] = _injected[pname]
        try:
            if inspect.iscoroutinefunction(self._func):
                return await self._func(**validated)
            return self._func(**validated)
        except (ToolArgumentError, ToolExecutionError):
            raise  # already domain errors — let them propagate unchanged
        except (
            FileNotFoundError,
            FileExistsError,
            IsADirectoryError,
            NotADirectoryError,
            OSError,
            ValueError,
        ) as exc:
            # Me message already clear — no need add noise
            raise ToolExecutionError(str(exc)) from exc
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool '{self.name}' raised {type(exc).__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Schema / definition builder
    # ------------------------------------------------------------------

    def _build(self) -> tuple[type[BaseModel], dict[str, Any], set[str]]:
        func = self._func
        sig = inspect.signature(func)

        # Description: custom override or the full docstring (use-case focused)
        raw_doc = inspect.getdoc(func) or ""
        description = self._custom_description or raw_doc.strip()

        # include_extras=True preserves Annotated[..., Field(...)] wrappers so
        # Pydantic picks up Field metadata (description, constraints) when
        # generating the JSON Schema.
        type_hints = get_type_hints(func, include_extras=True)

        fields: dict[str, Any] = {}
        injected_params: set[str] = set()

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            annotation = type_hints.get(param_name, Any)
            # Skip InjectedArg params — they are not part of the LLM schema
            if _is_injected(annotation):
                injected_params.add(param_name)
                continue
            default = (
                param.default if param.default is not inspect.Parameter.empty else ...
            )
            fields[param_name] = (annotation, default)

        ParameterModel = create_model(f"{self.name}_parameters", **fields)
        schema = ParameterModel.model_json_schema()

        # Resolve $ref pointers — Pydantic emits $defs + $ref for nested
        # models (e.g. list[SomeModel]).  Gemini and other providers reject
        # $ref, so we inline every reference and drop the $defs block.
        schema = _resolve_refs(schema)

        properties: dict[str, Any] = schema.get("properties", {})
        required: list[str] = schema.get("required", [])

        # Strip Pydantic-generated noise (title on each property)
        for prop in properties.values():
            prop.pop("title", None)

        definition: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

        return ParameterModel, definition, injected_params


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------


@overload
def tool(func: Callable) -> Tool: ...


@overload
def tool(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable], Tool]: ...


def tool(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Tool | Callable[[Callable], Tool]:
    """Decorator that converts a function into a :class:`Tool`.

    Parameter descriptions belong on the signature via
    ``Annotated[type, Field(description=...)]``.
    The docstring should describe the tool's use case for the LLM.

    Can be used with or without arguments::

        @tool
        def my_func(
            x: Annotated[int, Field(description="The input value.")],
        ) -> str:
            \"\"\"Convert a number to its string representation.\"\"\"
            ...

        @tool(name="custom")
        def my_func(...): ...

    Args:
        func: The function to wrap (only when used as a bare ``@tool``).
        name: Override the tool name (defaults to the function name).
        description: Override the tool description (defaults to the docstring).

    Returns:
        A :class:`Tool` instance, or a decorator that returns one.
    """
    if func is not None:
        # Used as bare @tool (no parentheses)
        return Tool(func)

    # Used as @tool(...) with keyword arguments
    def decorator(f: Callable) -> Tool:
        return Tool(f, name=name, description=description)

    return decorator
