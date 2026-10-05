"""
registry.py: how Python functions become tools the model can call.

Recap (see agent/loop.py for the full picture): the model can't run code.
We DESCRIBE functions to it as JSON Schema; it replies "please call X with
these arguments"; our code checks the request and runs the real function.

Phase 0 wrote those JSON descriptions by hand. Now a decorator builds them
from the function itself:

    @tool(tier=Tier.READ)
    def get_weather(place: Annotated[str | None, Field(description="...")] = None) -> dict:
        '''Current conditions and forecast.'''        <- becomes the description
        ...

  - the docstring        -> the tool's description
  - parameter names      -> argument names
  - type hints           -> argument types (str, int, ...)
  - Field(description=)  -> per-argument help text the model reads
  - defaults             -> which arguments are optional

Pydantic (the validation library FastAPI also uses) turns that into JSON
Schema, and later checks the model's arguments against it BEFORE the
function runs. A wrong type, or an argument name that doesn't exist, comes
back to the model as a readable error.

Permission tiers (design doc, mechanism 3): every tool must declare one
(there is deliberately no default, so a write tool can't slip in as READ).
  READ     runs immediately (look things up)
  PROPOSE  a write; will wait for your approval (Phase 4, refused for now)
  HANDOFF  money or irreversible; the app never runs it, it hands you a link
The tier is enforced HERE in code, so no prompt wording can bypass it.
"""
import inspect
import json
from dataclasses import dataclass
from enum import Enum
from typing import Callable, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError, create_model


class Tier(str, Enum):
    READ = "read"
    PROPOSE = "propose"
    HANDOFF = "handoff"


@dataclass
class Tool:
    name: str
    description: str
    tier: Tier
    fn: Callable
    args_model: type[BaseModel]  # Pydantic class describing the arguments


# name -> Tool. Filled in as tool modules are imported (see tools/__init__.py).
TOOLS: dict[str, Tool] = {}


def tool(*, tier: Tier):
    """Decorator that registers a function as a tool.

    Usage:  @tool(tier=Tier.READ)  or  @tool(tier=Tier.PROPOSE)
    The `*` makes `tier` keyword-only and required, so a bare `@tool` (which
    would silently register nothing) fails loudly instead.
    It returns the function unchanged, so you can still call it normally.
    """
    def register(fn: Callable) -> Callable:
        # include_extras=True keeps Annotated[...] so Field descriptions survive.
        hints = get_type_hints(fn, include_extras=True)
        fields = {}
        for name, param in inspect.signature(fn).parameters.items():
            annotation = hints.get(name, str)
            # `...` is Pydantic's marker for "required" (no default value).
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[name] = (annotation, default)

        # Build a Pydantic class on the fly, e.g. class get_weather_args(BaseModel): place: str | None = None
        # extra="forbid": reject argument names the function doesn't have.
        # Without it, {"city": "Shanghai"} would be silently ignored and the
        # weather tool would happily return Berkeley's weather instead.
        args_model = create_model(f"{fn.__name__}_args", __config__=ConfigDict(extra="forbid"), **fields)

        TOOLS[fn.__name__] = Tool(
            name=fn.__name__,
            description=inspect.getdoc(fn) or "",
            tier=tier,
            fn=fn,
            args_model=args_model,
        )
        return fn
    return register


def schemas() -> list[dict]:
    """All tools in the format the chat completions API expects:
    [{"type": "function", "function": {"name", "description", "parameters"}}, ...]
    The model only ever sees this; never the Python code."""
    result = []
    for t in TOOLS.values():
        params = _simplify(t.args_model.model_json_schema())
        result.append({
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": params},
        })
    return result


def _simplify(schema: dict) -> dict:
    """Tidy Pydantic's JSON Schema into the plainest form every provider accepts.

    - drops "title" fields ("get_weather_args", "Place"): noise for the model
    - turns `str | None` (written as {"anyOf": [{"type": "string"}, {"type": "null"}]})
      into just {"type": "string"}. Optional-ness is already expressed by the
      argument not being in "required", and some providers reject anyOf.
    """
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
        options = [o for o in prop.get("anyOf", []) if o.get("type") != "null"]
        if "anyOf" in prop and len(options) == 1:
            del prop["anyOf"]
            prop.update(options[0])
        if prop.get("default", ...) is None:
            del prop["default"]
    return schema


@dataclass
class ToolResult:
    text: str  # what the model will read
    ok: bool   # False if the call was refused or failed (shown red in traces)


def run(name: str, arguments_json: str) -> ToolResult:
    """Execute one tool request from the model.

    name:            which tool the model asked for, e.g. "get_weather"
    arguments_json:  the arguments as a JSON *string* the model wrote,
                     e.g. '{"place": "Shanghai"}'

    Every problem (unknown tool, bad arguments, tool crashed, tier not
    allowed) comes back as an explanatory text instead of an exception.
    It goes to the model, which can usually fix its mistake next round.
    """
    t = TOOLS.get(name)
    if t is None:
        return ToolResult(f"Error: there is no tool called {name!r}.", ok=False)

    # The safety gate. Only READ tools run on their own.
    if t.tier is Tier.PROPOSE:
        return ToolResult(
            f"Not done: {name!r} changes something, so it needs Paul's approval. "
            "The approval queue arrives in a later phase, so nothing was changed.", ok=False)
    if t.tier is Tier.HANDOFF:
        return ToolResult(
            f"Not done: {name!r} involves money or can't be undone, so the app never runs it. "
            "Give Paul the details so he can do it himself.", ok=False)

    try:
        # Parse + validate in one step: JSON text -> checked Python object.
        args = t.args_model.model_validate_json(arguments_json or "{}")
    except ValidationError as e:
        return ToolResult(f"Error: invalid arguments for {name}: {e}", ok=False)

    try:
        # dict(args) gives {"place": "Shanghai"}; ** turns it into keyword arguments.
        result = t.fn(**dict(args))
    except Exception as e:
        return ToolResult(f"Error while running {name}: {type(e).__name__}: {e}", ok=False)

    # The model reads text. Strings pass through; dicts/lists become JSON.
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return ToolResult(text, ok=True)
