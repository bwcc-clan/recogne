from functools import reduce
from typing import Any

import pydantic
from discord.flags import BaseFlags
from utils import SingletonMeta


class UnsetType(metaclass=SingletonMeta):
    def __bool__(self):
        return False

    def __iter__(self):
        return
        yield

    def __repr__(self):
        return "Unset"


Unset = UnsetType()
UnsetField = pydantic.Field(default_factory=lambda: Unset)


class Link:
    """Creates a link to one or more info entries"""

    def __init__(
        self,
        path: str,
        values: dict[str, Any],
        multiple: bool = False,
        fallback: Any = None,
    ):
        """Initiate a link.

        A link is a reference to another value from an array. `path` is the
        path leading to this array. It will then filter out all values where
        all attributes match the given values, as specified in the `values`
        parameter. If `multiple` is `True` it will return all matches.
        Otherwise it will result a single object. If nothing is found, an
        empty list or `None` is returned instead.

        Parameters
        ----------
        path : str
            The path of the array
        values : Dict[str, Any]
            A mapping of attribute names and their respective values
        multiple : bool, optional
            Whether a list should be returned instead of a single object, by
            default False
        fallback : Any
            A value to fall back to in case no objects could be resolved
            with the given values. Use cautiously; it may cause problems
            when merging, by default None
        """
        self.values = values
        self.path = path
        self.multiple = multiple
        self.fallback = fallback

    def __str__(self):
        return ",".join([f"{attr}={val}" for attr, val in self.values.items()])

    def __repr__(self):
        return f'Link[{self.__str__()}{"..." if self.multiple else ""}]'

    def __eq__(self, other):
        if isinstance(other, Link):
            return self.values == other.values
        elif isinstance(other, dict):
            return other.items() <= self.values.items()
        return NotImplemented



class Flags(BaseFlags):
    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        self.value: int = value
        for key, value in kwargs.items():
            if key not in self.VALID_FLAGS:
                raise TypeError(f"{key!r} is not a valid flag name.")
            setattr(self, key, value)

    def is_subset(self, other: "Flags") -> bool:
        """Returns ``True`` if self has the same or fewer permissions as other."""
        if isinstance(other, Flags):
            return (self.value & other.value) == self.value
        else:
            raise TypeError(
                f"cannot compare {self.__class__.__name__} with {other.__class__.__name__}"
            )

    def is_superset(self, other: "Flags") -> bool:
        """Returns ``True`` if self has the same or more permissions as other."""
        if isinstance(other, Flags):
            return (self.value | other.value) == self.value
        else:
            raise TypeError(
                f"cannot compare {self.__class__.__name__} with {other.__class__.__name__}"
            )

    def is_strict_subset(self, other: "Flags") -> bool:
        """Returns ``True`` if the permissions on other are a strict subset of those on self."""
        return self.is_subset(other) and self != other

    def is_strict_superset(self, other: "Flags") -> bool:
        """Returns ``True`` if the permissions on other are a strict superset of those on self."""
        return self.is_superset(other) and self != other

    def __len__(self):
        i = 0
        for _, enabled in self:
            if enabled:
                i += 1
        return i

    def copy(self):
        return type(self)(self.value)

    __le__ = is_subset
    __ge__ = is_superset
    __lt__ = is_strict_subset
    __gt__ = is_strict_superset

    @classmethod
    def all(cls: type["Flags"]) -> "Flags":
        value = reduce(lambda a, b: a | b, cls.VALID_FLAGS.values())
        self = cls.__new__(cls)
        self.value = value
        return self

    @classmethod
    def none(cls: type["Flags"]) -> "Flags":
        self = cls.__new__(cls)
        self.value = self.DEFAULT_VALUE
        return self
