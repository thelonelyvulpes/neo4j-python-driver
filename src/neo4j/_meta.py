# Copyright (c) "Neo4j"
# Neo4j Sweden AB [https://neo4j.com]
#
# This file is part of Neo4j.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import annotations

import asyncio
import platform
import sys
import tracemalloc
import typing as t
from functools import wraps
from inspect import isclass
from warnings import warn


if t.TYPE_CHECKING:
    _FuncT = t.TypeVar("_FuncT", bound=t.Callable)


# Can be automatically overridden in builds
package = "neo4j"
version = "5.13.dev0"
deprecated_package = False


def _compute_bolt_agent() -> t.Dict[str, str]:
    def format_version_info(version_info):
        return "{}.{}.{}-{}-{}".format(*version_info)

    return {
        "product": f"neo4j-python/{version}",
        "platform":
            f"{platform.system() or 'Unknown'} "
            f"{platform.release() or 'unknown'}; "
            f"{platform.machine() or 'unknown'}",
        "language": f"Python/{format_version_info(sys.version_info)}",
        "language_details":
            f"{platform.python_implementation()}; "
            f"{format_version_info(sys.implementation.version)} "
            f"({', '.join(platform.python_build())}) "
            f"[{platform.python_compiler()}]"
    }


BOLT_AGENT_DICT = _compute_bolt_agent()


def _compute_user_agent() -> str:
    template = "neo4j-python/{} Python/{}.{}.{}-{}-{} ({})"
    fields = (version,) + tuple(sys.version_info) + (sys.platform,)
    return template.format(*fields)


USER_AGENT = _compute_user_agent()


# TODO: 6.0 - remove this function
def get_user_agent():
    """ Obtain the default user agent string sent to the server after
    a successful handshake.
    """
    return USER_AGENT


def _id(x):
    return x


def copy_signature(_: _FuncT) -> t.Callable[[t.Callable], _FuncT]:
    return _id


def deprecation_warn(message, stack_level=1):
    warn(message, category=DeprecationWarning, stacklevel=stack_level + 1)


def deprecated(message: str) -> t.Callable[[_FuncT], _FuncT]:
    """ Decorator for deprecating functions and methods.

    ::

        @deprecated("'foo' has been deprecated in favour of 'bar'")
        def foo(x):
            pass

    """
    return _make_warning_decorator(message, deprecation_warn)


def deprecated_property(message: str):
    def decorator(f):
        return property(deprecated(message)(f))
    return t.cast(property, decorator)


class ExperimentalWarning(Warning):
    """ Base class for warnings about experimental features.

    .. deprecated:: 5.8
        we now use "preview" instead of "experimental":
        :class:`.PreviewWarning`.
    """


def experimental_warn(message, stack_level=1):
    warn(message, category=ExperimentalWarning, stacklevel=stack_level + 1)


def experimental(message) -> t.Callable[[_FuncT], _FuncT]:
    """ Decorator for tagging experimental functions and methods.

    ::

        @experimental("'foo' is an experimental function and may be "
                      "removed in a future release")
        def foo(x):
            pass

    .. deprecated:: 5.8
        we now use "preview" instead of "experimental".
    """
    return _make_warning_decorator(message, experimental_warn)


class PreviewWarning(Warning):
    """A driver feature in preview has been used.

    It might be changed without following the deprecation policy.
    See also https://github.com/neo4j/neo4j-python-driver/wiki/preview-features
    """


def preview_warn(message, stack_level=1):
    message += (
        " It might be changed without following the deprecation policy. "
        "See also "
        "https://github.com/neo4j/neo4j-python-driver/wiki/preview-features."
    )
    warn(message, category=PreviewWarning, stacklevel=stack_level + 1)


def preview(message) -> t.Callable[[_FuncT], _FuncT]:
    """
    Decorator for tagging preview functions and methods.

        @preview("foo is a preview.")
        def foo(x):
            pass
    """
    return _make_warning_decorator(message, preview_warn)


if t.TYPE_CHECKING:
    class _WarningFunc(t.Protocol):
        def __call__(self, message: str, stack_level: int = 1) -> None:
            ...
else:
    _WarningFunc = object


def _make_warning_decorator(
    message: str,
    warning_func: _WarningFunc,
) -> t.Callable[[_FuncT], _FuncT]:
    def decorator(f):
        if asyncio.iscoroutinefunction(f):
            @wraps(f)
            async def inner(*args, **kwargs):
                warning_func(message, stack_level=2)
                return await f(*args, **kwargs)

            inner._without_warning = f
            return inner
        if isclass(f):
            if hasattr(f, "__init__"):
                original_init = f.__init__

                @wraps(original_init)
                def inner(self, *args, **kwargs):
                    warning_func(message, stack_level=2)
                    return original_init(self, *args, **kwargs)

                def _without_warning(cls, *args, **kwargs):
                    obj = cls.__new__(cls, *args, **kwargs)
                    original_init(obj, *args, **kwargs)
                    return obj

                f.__init__ = inner
                f._without_warning = classmethod(_without_warning)
                return f
            raise TypeError(
                "Cannot decorate class without __init__"
            )
        else:
            @wraps(f)
            def inner(*args, **kwargs):
                warning_func(message, stack_level=2)
                return f(*args, **kwargs)

            inner._without_warning = f
            return inner

    return decorator


def unclosed_resource_warn(obj):
    msg = f"Unclosed {obj!r}."
    trace = tracemalloc.get_object_traceback(obj)
    if trace:
        msg += "\nObject allocated at (most recent call last):\n"
        msg += "\n".join(trace.format())
    else:
        msg += "\nEnable tracemalloc to get the object allocation traceback."
    warn(msg, ResourceWarning, stacklevel=2, source=obj)
