"""Central registry for ALICE runtime capabilities.

Registration is intentionally distinct from runtime verification: the registry
records what is callable and its declared safety/argument contract, while the
capability manager and postcondition system remain the authorities for whether
an operation is available and verified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import math
import threading
import time
from copy import deepcopy
from typing import Any


_ALLOWED_RISKS = {"read", "write", "execute", "external", "financial", "system"}


def _annotation_name(annotation: Any) -> str:
    if annotation is inspect.Signature.empty:
        return "unknown"
    return getattr(annotation, "__name__", str(annotation))


def _validate_json_schema(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    """Validate the deliberately supported JSON Schema subset used by tools.

    Unsupported schema keywords are rejected at registration rather than silently
    ignored. This keeps the advertised contract enforceable and predictable.
    """
    allowed = {
        "type", "properties", "required", "additionalProperties", "enum",
        "minimum", "maximum", "minLength", "maxLength", "items",
        "minItems", "maxItems", "description", "title", "source",
    }
    unknown = set(schema) - allowed
    if unknown:
        raise ValueError(f"Unsupported input schema keywords at {path}: {sorted(unknown)}")

    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    type_checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    if types:
        if any(t not in type_checks for t in types):
            raise ValueError(f"Unsupported schema type at {path}: {expected}")
        if not any(type_checks[t](value) for t in types):
            raise ToolArgumentError(f"{path} must be of type {' or '.join(types)}")

    if "enum" in schema and value not in schema["enum"]:
        raise ToolArgumentError(f"{path} must be one of the permitted values")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValueError(f"Invalid object schema at {path}")
        missing = [key for key in required if key not in value]
        if missing:
            raise ToolArgumentError(f"{path} missing required properties: {', '.join(missing)}")
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                child = properties[key]
                if not isinstance(child, dict):
                    raise ValueError(f"Invalid property schema for {path}.{key}")
                _validate_json_schema(item, child, f"{path}.{key}")
            elif additional is False:
                raise ToolArgumentError(f"{path} contains unexpected property: {key}")
            elif isinstance(additional, dict):
                _validate_json_schema(item, additional, f"{path}.{key}")

    if isinstance(value, (str, list)):
        length = len(value)
        for key, comparator in (("minLength" if isinstance(value, str) else "minItems", lambda a, b: a < b),
                                ("maxLength" if isinstance(value, str) else "maxItems", lambda a, b: a > b)):
            if key in schema and comparator(length, schema[key]):
                raise ToolArgumentError(f"{path} violates {key}")
        if isinstance(value, list) and isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                _validate_json_schema(item, schema["items"], f"{path}[{index}]")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolArgumentError(f"{path} must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolArgumentError(f"{path} must be at most {schema['maximum']}")


def _check_schema_definition(schema: dict[str, Any], path: str = "schema") -> None:
    allowed = {
        "type", "properties", "required", "additionalProperties", "enum",
        "minimum", "maximum", "minLength", "maxLength", "items",
        "minItems", "maxItems", "description", "title", "source",
    }
    unknown = set(schema) - allowed
    if unknown:
        raise ValueError(f"Unsupported input schema keywords at {path}: {sorted(unknown)}")
    expected = schema.get("type")
    valid_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not types or any(item not in valid_types for item in types):
            raise ValueError(f"{path}.type contains an unsupported type")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"{path}.properties must be an object")
    for key, child in properties.items():
        if not isinstance(key, str) or not isinstance(child, dict):
            raise ValueError(f"{path}.properties entries must map strings to schema objects")
        _check_schema_definition(child, f"{path}.properties.{key}")
    required = schema.get("required", [])
    if (not isinstance(required, list) or
            not all(isinstance(item, str) for item in required) or
            len(required) != len(set(required))):
        raise ValueError(f"{path}.required must contain unique strings")
    unknown_required = set(required) - set(properties)
    if unknown_required:
        raise ValueError(f"{path}.required references undefined properties: {sorted(unknown_required)}")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError(f"{path}.enum must be a non-empty list")
    import math
    for key in ("minimum", "maximum"):
        if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], (int, float)) or not math.isfinite(schema[key])):
            raise ValueError(f"{path}.{key} must be a finite number")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], int) or schema[key] < 0):
            raise ValueError(f"{path}.{key} must be a non-negative integer")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        raise ValueError(f"{path}.minimum cannot exceed maximum")
    for lower, upper in (("minLength", "maxLength"), ("minItems", "maxItems")):
        if lower in schema and upper in schema and schema[lower] > schema[upper]:
            raise ValueError(f"{path}.{lower} cannot exceed {upper}")
    if "items" in schema and not isinstance(schema["items"], dict):
        raise ValueError(f"{path}.items must be a schema object")
    if "items" in schema and expected not in (None, "array") and expected != ["array"]:
        raise ValueError(f"{path}.items requires type=array")
    additional = schema.get("additionalProperties", True)
    if isinstance(additional, dict):
        _check_schema_definition(additional, f"{path}.additionalProperties")
    if isinstance(schema.get("items"), dict):
        _check_schema_definition(schema["items"], f"{path}.items")


def _input_schema(function: Any) -> dict[str, Any]:
    """Build a conservative JSON-schema-like signature description.

    This is descriptive rather than a claim that arbitrary Python annotations
    are fully enforceable JSON schemas. Actual argument binding is performed
    with ``inspect.Signature.bind`` immediately before invocation.
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "required": [], "additionalProperties": False,
                "source": "signature_unavailable"}
    properties: dict[str, Any] = {}
    required: list[str] = []
    accepts_kwargs = False
    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_kwargs = True
            continue
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.POSITIONAL_ONLY):
            # Registry calls are keyword-based. Positional-only/variadic
            # positional callables cannot be safely represented as tool APIs.
            continue
        item: dict[str, Any] = {"python_type": _annotation_name(parameter.annotation)}
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        else:
            try:
                item["default"] = parameter.default if isinstance(parameter.default, (str, int, float, bool, type(None))) else repr(parameter.default)
            except Exception:
                item["default"] = "<unavailable>"
        properties[name] = item
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": accepts_kwargs, "source": "python_signature"}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: object
    risk: str = "read"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    timeout_seconds: float = 30.0
    cancellation_supported: bool = False
    preconditions: tuple[str, ...] = ()
    verification: str = "not_declared"


class ToolArgumentError(ValueError):
    """A registered tool was called with arguments outside its callable contract."""


class ToolOutputError(ValueError):
    """A registered tool returned a value outside its declared output contract."""


class ToolTimeoutError(TimeoutError):
    """A cooperative tool exceeded its execution budget after receiving a stop signal."""


class _CombinedCancellationEvent:
    """Read-only event facade combining caller cancellation and timeout."""

    def __init__(self, external, timed_out):
        self._external = external
        self._timed_out = timed_out

    def is_set(self):
        return bool(self._timed_out.is_set() or
                    (self._external is not None and self._external.is_set()))

    def wait(self, timeout=None):
        # Poll both sources without assuming the caller's event implementation
        # exposes a multi-event wait primitive.
        end = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while not self.is_set():
            if end is not None and time.monotonic() >= end:
                return False
            time.sleep(0.01)
        return True


class ToolRegistry:
    def __init__(self, capability_manager=None):
        self.tools: dict[str, Tool] = {}
        # Keep enforcement contracts in registry-owned snapshots. Tool objects
        # and inventory/describe results are intentionally inspectable, so their
        # nested dictionaries must never become the source of execution policy.
        self._input_contracts: dict[str, dict[str, Any]] = {}
        self._output_contracts: dict[str, dict[str, Any] | None] = {}
        self.capability_manager = capability_manager

    def add(
        self, name, description, fn, risk="read", *, input_schema=None,
        output_schema=None, timeout_seconds=30.0, cancellation_supported=False,
        preconditions=(), verification="not_declared",
    ):
        key = str(name or "").strip()
        if not key or len(key) > 128:
            raise ValueError("Tool name must contain 1-128 non-whitespace characters")
        if not callable(fn):
            raise TypeError(f"Tool '{key}' must register a callable")
        if risk not in _ALLOWED_RISKS:
            raise ValueError(f"Tool '{key}' has unsupported risk classification: {risk}")
        if isinstance(timeout_seconds, bool):
            raise ValueError("Tool timeout_seconds must be a positive finite number")
        if not isinstance(cancellation_supported, bool):
            raise ValueError("Tool cancellation_supported must be a boolean")
        if cancellation_supported:
            try:
                parameters = inspect.signature(fn).parameters
            except (TypeError, ValueError) as exc:
                raise ValueError("Cooperative cancellation requires an inspectable callable") from exc
            cancel_parameter = parameters.get("cancel_event")
            if cancel_parameter is None or cancel_parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.VAR_POSITIONAL,
            ):
                raise ValueError("Cooperative cancellation requires a keyword cancel_event parameter")
        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Tool timeout_seconds must be a positive finite number") from exc
        if timeout <= 0 or timeout == float("inf") or timeout != timeout:
            raise ValueError("Tool timeout_seconds must be a positive finite number")
        schema = dict(input_schema) if input_schema is not None else _input_schema(fn)
        if input_schema is not None:
            schema["source"] = "explicit_schema"
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("Tool input_schema must describe an object")
        if input_schema is not None:
            # Validate schema shape early; value validation happens before invocation.
            _check_schema_definition(schema)
            if not isinstance(schema.get("required", []), list) or not all(
                isinstance(item, str) for item in schema.get("required", [])
            ):
                raise ValueError("Tool input_schema.required must be a list of strings")
            _validate_json_schema({}, {
                "type": "object",
                "properties": schema.get("properties", {}),
                "additionalProperties": schema.get("additionalProperties", True),
            }, "schema")
        if not isinstance(preconditions, (tuple, list)):
            raise ValueError("Tool preconditions must be a list or tuple")
        contract_snapshot = deepcopy(schema)
        if output_schema is not None:
            if not isinstance(output_schema, dict):
                raise ValueError("Tool output_schema must be a schema object")
            _check_schema_definition(output_schema, "output_schema")
            output_snapshot = deepcopy(output_schema)
        else:
            output_snapshot = None
        tool = Tool(
            name=key,
            description=str(description or ""),
            fn=fn,
            risk=risk,
            input_schema=deepcopy(contract_snapshot),
            output_schema=deepcopy(output_snapshot),
            timeout_seconds=timeout,
            cancellation_supported=cancellation_supported,
            preconditions=tuple(str(item) for item in preconditions),
            verification=str(verification or "not_declared"),
        )
        self.tools[key] = tool
        self._input_contracts[key] = contract_snapshot
        self._output_contracts[key] = output_snapshot
        manager = self.capability_manager
        existing = manager.get(key) if manager is not None else None
        if manager is not None and (
            existing is None
            or (existing.get("kind") == "acquired_candidate" and not existing.get("configured", True))
        ):
            manager.register(
                key,
                description,
                kind="runtime_tool",
                source="tool_registry",
                permissions=[risk],
                configured=True,
            )
        bind = getattr(manager, "bind_runtime_callable", None)
        if callable(bind):
            bind(key, fn)
        return tool

    def describe(self):
        return {
            key: {
                "description": tool.description,
                "risk": tool.risk,
                "input_schema": deepcopy(self._input_contracts.get(key, tool.input_schema)),
                "output_schema": deepcopy(self._output_contracts.get(key)),
                "timeout_seconds": tool.timeout_seconds,
                "timeout_enforcement": ("cooperative_signal_only" if tool.cancellation_supported else "not_enforced_for_in_process_callable"),
                "cancellation_supported": tool.cancellation_supported,
                "cancellation_mode": "cooperative_token" if tool.cancellation_supported else "unsupported",
                "preconditions": list(tool.preconditions),
                "verification": tool.verification,
            }
            for key, tool in self.tools.items()
        }

    def run(self, name, args=None):
        tool = self.tools.get(name)
        if tool is None:
            raise ValueError("Unknown tool: " + str(name))
        return self.run_registered(tool, args)

    def run_registered(self, tool, args=None, *, cancel_event=None, timeout_seconds=None):
        """Execute the exact registered tool after validating its arguments.

        A cancellation event is forwarded only to callables that explicitly
        registered cooperative cancellation support. It is a request token,
        not a mechanism for forcibly interrupting Python code.
        """
        if not isinstance(tool, Tool) or self.tools.get(tool.name) is not tool:
            raise ValueError("Registered tool changed before execution")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ToolArgumentError("Tool arguments must be an object")
        contract = self._input_contracts.get(tool.name)
        if contract is None:
            raise ValueError("Registered tool contract is unavailable")
        if contract.get("source") == "explicit_schema":
            _validate_json_schema(args, contract)
        call_args = dict(args)
        try:
            signature = inspect.signature(tool.fn)
            if tool.cancellation_supported:
                if "cancel_event" not in signature.parameters:
                    raise ToolArgumentError(
                        f"Tool '{tool.name}' no longer accepts its declared cancel_event parameter"
                    )
            signature.bind(**call_args, **({"cancel_event": None} if tool.cancellation_supported else {}))
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ToolArgumentError):
                raise
            raise ToolArgumentError(f"Invalid arguments for tool '{tool.name}': {exc}") from exc

        result = None
        if tool.cancellation_supported:
            budget = tool.timeout_seconds if timeout_seconds is None else min(tool.timeout_seconds, timeout_seconds)
            if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget <= 0:
                raise ValueError("Execution timeout must be a positive finite number")
            timed_out = threading.Event()
            combined_event = _CombinedCancellationEvent(cancel_event, timed_out)
            timer = threading.Timer(float(budget), timed_out.set)
            call_args["cancel_event"] = combined_event
            timer.daemon = True
            timer.start()
            try:
                result = tool.fn(**call_args)
            finally:
                timer.cancel()
            if timed_out.is_set():
                raise ToolTimeoutError(
                    f"Tool '{tool.name}' exceeded its {float(budget):g}s cooperative execution budget; "
                    "the callable returned after receiving the timeout signal"
                )
        else:
            result = tool.fn(**call_args)
        output_contract = self._output_contracts.get(tool.name)
        if output_contract is not None:
            try:
                _validate_json_schema(result, output_contract, "result")
            except ToolArgumentError as exc:
                # The callable has already run. Report the contract violation
                # explicitly; callers must not interpret this as proof that no
                # external side effect occurred.
                raise ToolOutputError(f"Tool '{tool.name}' returned an invalid result: {exc}") from exc
        return result

    def get(self, name):
        return self.tools.get(name)

    def inventory(self):
        """Return live tool contracts plus independent capability evidence."""
        items = []
        for name, tool in sorted(self.tools.items()):
            capability = (
                self.capability_manager.status(name)
                if self.capability_manager is not None
                else {"known": False, "status": "unverified", "verified": False}
            )
            items.append({
                "name": name,
                "description": tool.description,
                "risk": tool.risk,
                "input_schema": deepcopy(self._input_contracts.get(name, tool.input_schema)),
                "output_schema": deepcopy(self._output_contracts.get(name)),
                "timeout_seconds": tool.timeout_seconds,
                "timeout_enforcement": ("cooperative_signal_only" if tool.cancellation_supported else "not_enforced_for_in_process_callable"),
                "cancellation_supported": tool.cancellation_supported,
                "cancellation_mode": "cooperative_token" if tool.cancellation_supported else "unsupported",
                "preconditions": list(tool.preconditions),
                "verification": tool.verification,
                "capability": capability,
            })
        return items
