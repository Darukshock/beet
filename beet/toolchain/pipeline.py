__all__ = [
    "GenericPipeline",
    "Task",
    "GenericPlugin",
    "GenericPluginSpec",
    "PipelineFallthroughException",
    "FormattedPipelineException",
    "PluginError",
    "PluginImportError",
]


from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    Protocol,
    Set,
    TypeVar,
    Union,
    cast,
)

from beet.core.utils import import_from_string

from .utils import format_obj

T = TypeVar("T")
ContextType = TypeVar("ContextType", contravariant=True)


class GenericPlugin(Protocol[ContextType]):
    """Protocol for detecting plugins."""

    def __call__(self, ctx: ContextType, /) -> Any:
        ...


GenericPluginSpec = Union[GenericPlugin[ContextType], str]


class PipelineFallthroughException(Exception):
    """Exceptions inheriting from this class will fall through the pipeline exception handling."""


class FormattedPipelineException(PipelineFallthroughException):
    """Exceptions inheriting from this class can expose a formatted message."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.message = ""
        self.format_cause = False


class PluginError(FormattedPipelineException):
    """Raised when a plugin raises an exception."""

    def __init__(self, plugin: Any):
        super().__init__(plugin)
        self.message = f"Plugin {format_obj(plugin)} raised an exception."
        self.format_cause = True


class PluginImportError(FormattedPipelineException):
    """Raised when a plugin couldn't be imported."""

    def __init__(self, plugin: Any):
        super().__init__(plugin)
        self.message = f"Couldn't import plugin {format_obj(plugin)}."
        self.format_cause = True


@dataclass
class Task(Generic[T]):
    """A unit of work generated by the pipeline."""

    plugin: GenericPlugin[T]
    iterator: Optional[Iterator[Any]] = None

    def advance(self, ctx: T) -> Optional["Task[T]"]:
        """Make progress on the task and return it unless no more work is necessary."""
        try:
            if self.iterator is None:
                result = self.plugin(ctx)
                self.iterator = iter(
                    cast(Iterable[Any], result) if isinstance(result, Iterable) else []
                )
            for _ in self.iterator:
                return self
        except PipelineFallthroughException:
            raise
        except Exception as exc:
            raise PluginError(self.plugin) from exc.with_traceback(
                getattr(exc.__traceback__, "tb_next", exc.__traceback__)
            )
        return None


@dataclass
class GenericPipeline(Generic[T]):
    """The plugin execution engine."""

    ctx: T
    default_symbol: str = "beet_default"

    whitelist: Optional[List[str]] = None
    plugins: Set[GenericPlugin[T]] = field(default_factory=set)
    tasks: List[Task[T]] = field(default_factory=list)

    def require(self, *args: GenericPluginSpec[T]):
        """Execute the specified plugin."""
        for spec in args:
            plugin = self.resolve(spec)
            if plugin in self.plugins:
                return

            self.plugins.add(plugin)

            if remaining_work := Task(plugin).advance(self.ctx):
                self.tasks.append(remaining_work)

    def resolve(self, spec: GenericPluginSpec[T]) -> GenericPlugin[T]:
        """Return the imported plugin if the argument is a dotted path."""
        try:
            return (
                import_from_string(
                    dotted_path=spec,
                    default_member=self.default_symbol,
                    whitelist=self.whitelist,
                )
                if isinstance(spec, str)
                else spec
            )
        except PipelineFallthroughException:
            raise
        except Exception as exc:
            raise PluginImportError(spec) from exc

    def run(self, specs: Iterable[GenericPluginSpec[T]] = ()):
        """Run the specified plugins."""
        for spec in specs:
            self.require(spec)

        while self.tasks:
            if remaining_work := self.tasks.pop().advance(self.ctx):
                self.tasks.append(remaining_work)
