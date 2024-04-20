from collections import UserList
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum, unique
from inspect import isclass
from typing import TYPE_CHECKING, Any, ClassVar, Generator, List, Union

import pydantic
from discord.flags import fill_with_flags, flag_value
from rcon.info.types import Flags, Link, Unset, UnsetField

if TYPE_CHECKING:
    from ..storage import LogLine


obj_setattr = object.__setattr__
obj_getattr = object.__getattribute__


class ModelTree(pydantic.BaseModel):
    class Config:
        arbitrary_types_allowed = True

    def __repr_args__(self):
        return [
            (k, obj_getattr(self, k))
            for k in self.__fields__.keys()
            if self.__fields__[k].field_info.repr
        ]

    @property
    def root(self) -> "InfoHopper":
        return getattr(self, "__hopper__", self)

    def __iter__(self) -> Generator[tuple, None, None]:
        for attr in self.__fields__:
            yield (attr, obj_getattr(self, attr))

    def __contains__(self, item):
        if isinstance(item, ModelTree):
            return item in self.flatten()
        else:
            return False

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, pydantic.BaseModel):
            return dict(self) == dict(other)
        else:
            return dict(self) == other

    def flatten(self):
        """Create a generator of all models attached
        to this one

        Yields
        ------
        ModelTree
            An attached model
        """
        for key, value in self:
            if isinstance(value, ModelTree):
                if hasattr(self, "__links__") and not self.__links__.get(key):
                    yield value
                    yield from value.flatten()
            elif isinstance(value, InfoModelArray):
                for item in value:
                    yield item
                    yield from item.flatten()

    def is_mutable(self):
        """Whether the model is mutable or not

        Returns
        -------
        bool
            Whether the model is mutable
        """
        return not self.root.__solid__ and self.__config__.allow_mutation

    def set_mutable(self, _bool, force=False):
        """Change this model's mutability, including all of
        its children.

        Parameters
        ----------
        _bool : bool
            Whether this model should be mutable
        force : bool, optional
            Whether to continue with the operation even if in
            theory it shouldn't make a difference, by default
            False
        """
        root = self.root
        _bool = bool(_bool)
        if root.__solid__ != _bool or force:
            for model in root.flatten():
                model.__config__.allow_mutation = False
            root.__solid__ = _bool

    @contextmanager
    def ignore_immutability(self):
        """A context manager to make this model temporarily mutable
        even if it shouldn't."""
        is_mutable = self.is_mutable()
        try:
            if not is_mutable:
                self.set_mutable(True)
            yield self
        finally:
            if not is_mutable:
                self.set_mutable(False)

    def merge(self, other: "ModelTree"):
        """Merge another model into this one.

        This model will inherit all of the other model with
        the other model taking priority, while the other model
        stays untouched.

        Parameters
        ----------
        other : ModelTree
            The other ModelTree to merge from

        Raises
        ------
        TypeError
            Models are not of same class
        TypeError
            This model is not mutable
        """
        if not isinstance(other, self.__class__):
            raise TypeError(
                "Info classes are not of same type: %s and %s"
                % (type(self).__name__, type(other).__name__)
            )
        if not self.is_mutable():
            raise TypeError("Model must be mutable to merge another into it")

        for attr in other.__fields__:
            self_val = self.get(attr, raw=True)
            other_val = other.get(attr, raw=True)

            if other_val is Unset:
                # Do nothing
                continue

            if self_val is Unset:
                # Copy other to self
                setattr(self, attr, other_val)

            elif isinstance(self_val, ModelTree):
                if isinstance(other_val, self_val.__class__):
                    # Merge other into self
                    self_val.merge(other_val)
                else:
                    # getLogger().warning('Skipping attempt to merge %s into %s', type(other_val).__name__, type(self_val).__name__)
                    pass

            elif isinstance(other_val, InfoModelArray) and isinstance(
                self_val, InfoModelArray
            ):
                for other_iter in other_val:
                    if isinstance(other_iter, InfoModel):
                        # Find matching model and merge
                        attrs = {
                            attr: other_iter.get(attr)
                            for attr in other_iter.__key_fields__
                            if other_iter.get(attr)
                        }
                        self_iter = self._get(
                            self_val, single=True, ignore_unknown=True, **attrs
                        )
                        if self_iter:
                            self_iter.merge(other_iter)
                        else:
                            # getLogger().warning('Could not match %s %s to existing record, discarding...', type(other_iter).__name__, attrs)
                            pass

    def _get(
        self, key, multiple=False, ignore_unknown=False, **filters
    ) -> Union["ModelTree", "InfoModel", "InfoModelArray"]:
        """Return a model from one of this model's `InfoModelArray`s.

        `**filters` contains a mapping of attributes and values to
        filter for. The array to filter is `key`. If `key` is a string
        it will be interpret as the name of one of this model's
        attributes.

        Parameters
        ----------
        key : Union[InfoModelArray, str]
            An array or attribute name
        multiple : bool, optional
            Whether a list of matches should be returned, by default
            False
        ignore_unknown : bool, optional
            Whether to ignore filter keys that are not recognized as
            a property, by default False
        **filters : dict
            A mapping of attribute names and values to filter for

        Returns
        -------
        Union[ModelTree, InfoModel, InfoModelArray]
            The model or array of models found

        Raises
        ------
        TypeError
            The `key` attribute does not point to an `InfoModelArray`
        """
        if isinstance(key, InfoModelArray):
            array = key
        else:
            array = self.get(key, raw=True)

        if array is Unset:
            array = InfoModelArray()
        elif not isinstance(array, InfoModelArray):
            raise TypeError(
                "%s must point to an InfoModelArray, not %s" % (key, type(array))
            )

        res = InfoModelArray(
            filter(lambda x: x.matches(ignore_unknown=ignore_unknown, **filters), array)
        )
        return res if multiple else (res[0] if res else None)

    def _add(self, key, *objects):
        """Add a model to one of this model's `InfoModelArray`s.

        Parameters
        ----------
        key : Union[InfoModelArray, str]
            An array or attribute name

        Returns
        -------
        InfoModelArray
            The new array

        Raises
        ------
        TypeError
            The `key` attribute does not point to an `InfoModelArray`
        """
        if isinstance(key, InfoModelArray):
            array = key
        else:
            array = self.get(key, raw=True)

        if array is Unset:
            array = InfoModelArray()
        elif not isinstance(array, InfoModelArray):
            raise TypeError(
                "%s must point to an InfoModelArray, not %s" % (key, type(array))
            )

        for obj in objects:
            array.append(obj)
        setattr(self, key, array)
        return array

    def get(self, name, default=None, raw=False):
        """Get one of this model's attributes.

        Parameters
        ----------
        name : str
            The name of the attribute
        default : bool, optional
            The value to return if the attribute is not found,
            by default None
        raw : bool, optional
            Whether to resolve links and `UnsetField`s, by default False

        Returns
        -------
        Any
            The returned value
        """
        try:
            if raw:
                return obj_getattr(self, name)
            else:
                return getattr(self, name, default)
        except AttributeError:
            return default

    def has(self, name):
        """Returns whether this model has an attribute with
        this name.

        Parameters
        ----------
        name : str
            The name of the attribute

        Returns
        -------
        bool
            Whether the attribute exists
        """
        return name in self.__fields__ and obj_getattr(self, name) is not Unset

    def to_dict(self, is_ref=False, exclude_unset=False) -> dict:
        """Cast this model to a dict.

        Parameters
        ----------
        is_ref : bool, optional
            Whether the model was obtained via a :class:`Link`.
            This will only return the key fields to
            avoid infinite recursion, by default False
        exclude_unset : bool, optional
            Whether to exclude variables that are left unset, by
            default False

        Returns
        -------
        dict
            The model as a dict
        """
        d = dict()
        key_fields = getattr(self, "__key_fields__", [])

        for attr in self.__fields__ if not is_ref or not key_fields else key_fields:
            val = self.get(attr, default=Unset)

            # if not is_ref and not key_fields and isinstance(val, pydantic.BaseModel):
            #    continue
            if exclude_unset and val == Unset:
                continue

            _is_ref = isinstance(self, InfoModel) and attr in self.__links__
            if isinstance(val, ModelTree):
                val = val.to_dict(is_ref=_is_ref, exclude_unset=exclude_unset)
            elif isinstance(val, InfoModelArray):
                val = [
                    v.to_dict(is_ref=_is_ref, exclude_unset=exclude_unset) for v in val
                ]
            d[attr] = val
        return d


class InfoModel(ModelTree):
    __scope_path__: ClassVar[str]
    __key_fields__: ClassVar[tuple[str, ...]]
    __hopper__: "InfoHopper"
    __links__: dict[str, Link]
    __created_at__: datetime

    def __init__(self, hopper: "InfoHopper", *args, **kwargs):
        _flat = hopper.flatten()
        self.__validate_values(kwargs.values(), _flat=_flat)

        self.update_forward_refs()
        super().__init__(*args, **kwargs)

        links = dict()
        for key, val in kwargs.items():
            if isinstance(val, Link):
                links[key] = val

        obj_setattr(self, "__hopper__", hopper)
        obj_setattr(self, "__links__", links)
        obj_setattr(self, "__created_at__", datetime.now(tz=timezone.utc))

    def __validate_values(self, values, _flat=None):
        for val in values:
            if isinstance(val, ModelTree):
                if _flat is None:
                    _flat = self.__hopper__.flatten()
                flat = list(_flat)
                if val in flat:
                    raise ValueError(
                        "%s is already part of tree. Use a Link instead."
                        % val.__class__.__name__
                    )
                self.__validate_values(dict(val).values(), _flat=_flat)

    def __getattribute__(self, name: str):
        if name in obj_getattr(self, "__fields__"):
            try:
                links = obj_getattr(self, "__links__")
                link = links.get(name)
            except Exception:
                link = None

            if link:
                res = self._get_link_value(link)
            else:
                res = super().__getattribute__(name)

            if res is Unset:
                raise AttributeError(
                    f'"{type(self).__name__}" has no attribute "{name}"'
                )
            return res
        else:
            return super().__getattribute__(name)

    def __setattr__(self, name, value):
        if isinstance(value, Link):
            return self._add_link(value, name)
        elif isinstance(value, ModelTree):
            self.__validate_values([value])
        super().__setattr__(name, value)
        obj_getattr(self, "__links__").pop(name, None)

    def __eq__(self, other):
        if isinstance(other, dict):
            d2 = other
        elif isinstance(other, InfoModel):
            if not isinstance(other, self.__class__) or not isinstance(
                self, other.__class__
            ):
                # raise TypeError("%s is no instance of %s or vice versa" % (other.__class__.__name__, self.__class__.__name__))
                return False
            d2 = other.get_key_attributes(exclude_unset=True)
        else:
            return NotImplemented

        d1 = self.get_key_attributes(exclude_unset=True)
        for k, v in d1.items():
            if k in d2:
                if d2[k] != v:
                    return False
        return True

    def _add_link(self, link: Link, name):
        super().__setattr__(name, link)
        self.__links__[name] = link

    def _get_link_value(self, link: Link):
        hopper: "InfoHopper" = obj_getattr(self, "__hopper__")
        res = hopper._get(link.path, multiple=link.multiple, **link.values)
        if not res and link.fallback:
            return link.fallback
        return res

    def create_link(self, with_fallback=False, hopper: "InfoHopper" = None):
        if not self.__key_fields__:
            raise TypeError("This model does not have any key fields specified")

        values = self.get_key_attributes(exclude_unset=True, exclude_links=True)
        if not values:
            raise ValueError("No key fields have values assigned")

        fallback = None
        if with_fallback:
            if hopper is None:
                fallback = type(self)(
                    self.__hopper__,
                    **self.get_key_attributes(exclude_unset=True, exclude_links=True),
                )
            elif isinstance(hopper, ModelTree):
                fallback = self.copy(hopper.root)
            else:
                raise TypeError(
                    "hopper must be an ModelTree, got %s" % type(hopper).__name__
                )

        return Link(self.__scope_path__, values, fallback=fallback)

    def copy(self, hopper: "InfoHopper"):
        new = type(self)(hopper)
        new.merge(self)
        return new

    def _get_raw_value(self, attr):
        res = self.get(attr, raw=True)
        if isinstance(res, Link):
            return res.values
        else:
            return res

    def get_key_attributes(self, exclude_unset=False, exclude_links=False):
        return {
            attr: self._get_raw_value(attr)
            for attr in self.__key_fields__
            if not (exclude_unset and self._get_raw_value(attr) == Unset)
            and not (exclude_links and self.__links__.get(attr))
        }

    @property
    def key_attribute(self):
        return tuple(
            self.get_key_attributes(exclude_unset=True, exclude_links=True).values()
        )[0]

    def matches(self, ignore_unknown=False, **filters):
        return all(
            self.get(key, raw=True) == value
            for key, value in filters.items()
            if not (ignore_unknown and self.get(key, default=Unset, raw=True) == Unset)
        )

    def args(self):
        return (self.get(attr) for attr in self.__fields__)


class InfoModelArray(UserList):
    def __init__(self, initlist=None) -> list[InfoModel]:
        self.data = []
        if initlist is not None:
            if isinstance(initlist, UserList):
                self.data[:] = initlist.data[:]
            else:
                if type(initlist) != type(self.data):  # noqa: E721
                    initlist = list(initlist)
                for value in initlist:
                    self.__validate(value)
                self.data[:] = initlist

    @staticmethod
    def __validate(value):
        if not isinstance(value, InfoModel):
            raise TypeError(
                "Sequence only allows InfoModel, not %s" % type(value).__name__
            )

    def __setitem__(self, index, value):
        self.__validate(value)
        return super().__setitem__(index, value)

    def __iadd__(self, other):
        if isinstance(other, UserList):
            self.data += other.data
        elif isinstance(other, type(self.data)):
            for value in other:
                self.__validate(value)
            self.data += other
        else:
            other = list(other)
            for value in other:
                self.__validate(value)
            self.data += other
        return self

    def append(self, item):
        self.__validate(item)
        self.data.append(item)

    def insert(self, i, item):
        self.__validate(item)
        self.data.insert(i, item)

    def extend(self, other):
        if isinstance(other, InfoModelArray):
            self.data.extend(other.data)
        else:
            if isinstance(other, UserList):
                other = other.data
            for value in other:
                self.__validate(value)
            self.data.extend(other)

class Player(InfoModel):
    __key_fields__ = ("steamid", "id", "name",)
    __scope_path__ = "players"

    steamid: str = UnsetField
    """The Steam64 ID of the player"""

    name: str = UnsetField
    """The name of the player"""

    id: Union[int, str] = UnsetField
    """An ID unique to the player"""

    ip: Union[str, None] = UnsetField
    """The IP address of the player"""

    team: Union["Team", Link, None] = UnsetField
    """The team the player is a part of"""

    squad: Union["Squad", Link, None] = UnsetField
    """The squad this player is a part of"""

    role: Union[str, None] = UnsetField
    """The role (often referred to as class) the player is using"""

    loadout: Union[str, None] = UnsetField
    """The loadout the player is using"""

    level: int = UnsetField
    """The level of the player"""

    kills: int = UnsetField
    """The number of kills the player has"""

    deaths: int = UnsetField
    """The number of deaths the player has"""

    assists: int = UnsetField
    """The number of assists the player has"""

    alive: bool = UnsetField
    """Whether the player is currently alive"""

    score: 'HLLPlayerScore' = UnsetField
    """The score of the player"""

    location: Any = UnsetField
    """The location of the player"""

    ping: int = UnsetField
    """The latency of the player in milliseconds"""

    is_vip: bool = UnsetField
    """Whether the player is a VIP"""

    joined_at: datetime = UnsetField
    """The time the player joined the server at"""

    is_spectator: bool = UnsetField
    """Whether the player is currently spectating"""

    is_incompatible_name: bool = False
    """Whether the name is expected to cause incompatibility issues"""

    def is_squad_leader(self) -> Union[bool, None]:
        """Whether the player is a squad leader, or None if not part of a squad"""
        squad = self.get('squad')
        if squad:
            leader = squad.get('leader')
            if leader:
                if self == leader:
                    return True
                else:
                    return False
        return None

    def __hash__(self):
        return hash(self.get('steamid') or self.get('name'))

    def __eq__(self, other):
        if isinstance(other, Player):
            return hash(self) == hash(other)
        else:
            return super().__eq__(other)

class HLLPlayerScore(pydantic.BaseModel):
    combat: int = UnsetField
    """The player's combat score"""

    offense: int = UnsetField
    """The player's offense score"""

    defense: int = UnsetField
    """The player's defense score"""

    support: int = UnsetField
    """The player's support score"""

class Squad(InfoModel):
    __key_fields__ = ("id", "name", "team")
    __scope_path__ = "squads"

    id: Union[int, str] = UnsetField
    """An ID unique to the squad"""

    leader: Union["Player", Link, None] = UnsetField
    """The leader of the squad"""

    creator: Union["Player", Link, None] = UnsetField
    """The creator of the squad"""

    name: str = UnsetField
    """The name of the squad"""

    type: str = UnsetField
    """The type of the squad"""

    private: bool = UnsetField
    """Whether the squad is private, commonly referred to as "locked" or "invite only\""""

    team: Union["Team", Link, None] = UnsetField
    """The team the squad belongs to"""

    players: Union[Sequence["Player"], Link] = UnsetField
    """All players part of the squad"""

    created_at: datetime = UnsetField
    """The time the squad was created at"""

class Team(InfoModel):
    __key_fields__ = ("id", "name",)
    __scope_path__ = "teams"

    id: Union[int, str] = UnsetField
    """An ID unique to the team"""

    leader: Union["Player", Link, None] = UnsetField
    """The leader of the team"""

    name: str = UnsetField
    """The name of the team"""

    squads: Union[Sequence["Squad"], Link] = UnsetField
    """All squads part of the team"""

    players: Union[Sequence["Player"], Link] = UnsetField
    """All players part of the team"""

    lives: int = UnsetField
    """The amount of lives (often referred to as tickets) left for this team"""

    score: int = UnsetField
    """The score of the team"""

    created_at: datetime = UnsetField
    """The time the team was created at"""

    def get_unassigned_players(self) -> Sequence["Player"]:
        """Get a list of players part of this team that are not part of a squad"""
        return [player for player in self.players if player.has('squad') and not player.squad]

class Server(InfoModel):
    __key_fields__ = ("name",)
    __scope_path__ = "server"

    name: str = UnsetField
    """The name of the server"""

    map: str = UnsetField
    """The name of the current map"""

    gamemode: str = UnsetField
    """The current gamemode"""

    next_map: str = UnsetField
    """The name of the upcoming map"""

    next_gamemode: str = UnsetField
    """The upcoming gamemode"""

    round_start: datetime = UnsetField
    """The time the current round started at"""

    round_end: datetime = UnsetField
    """The time the current round is estimated to end at"""

    state: str = UnsetField
    """The current gameplay state of the server, such as "end_of_round" or "warmup\""""

    queue_length: int = UnsetField
    """The amount of people currently waiting in queue"""

    ranked: bool = UnsetField
    """Whether the server is ranked or not"""

    vac_enabled: bool = UnsetField # Valve Anti Cheat
    """Whether the server utilises Valve Anti-Cheat"""

    pb_enabled: bool = UnsetField # Punkbuster
    """Whether the server utilises Punkbuster Anti-Cheat"""

    location: Any = UnsetField
    """The location of the server"""

    tickrate: float = UnsetField
    """The current tickrate of the server"""

    online_since: datetime = UnsetField
    """The time the server went online"""

    settings: 'ServerSettings' = UnsetField
    """The server's settings"""

class ServerSettings(InfoModel):
    __scope_path__ = "server.settings"

    rotation: Union[list[str], list[Any]] = UnsetField
    """A list of maps/layers currently in rotation"""

    require_password: bool = UnsetField
    """Whether the server requires a password to enter"""
    password: str = UnsetField
    """The password required to enter the server"""

    max_players: int = UnsetField
    """The maximum amount of players that can be on the server at once"""

    max_queue_length: int = UnsetField
    """The maximum amount of players that can be waiting in queue to enter the server at once"""

    max_vip_slots: int = UnsetField
    """The number of slots that the server holds reserved for VIPs"""

    time_dilation: float = UnsetField
    """The time dilation of the server"""

    idle_kick_time: timedelta = UnsetField
    """The time players can stay idle until kicked"""
    idle_kick_enabled: bool = UnsetField
    """Whether players get kicked for staying idle too long"""

    ping_threshold: Union[int, None] = UnsetField
    """The latency threshold in milliseconds past which players get kicked for a poor connection"""
    ping_threshold_enabled: bool = UnsetField
    """Whether players can get kicked for having a poor latency"""

    team_switch_cooldown: Union[timedelta, None] = UnsetField
    """The time players have to wait between switching teams"""
    team_switch_cooldown_enabled: bool = UnsetField
    """Whether there is a cooldown preventing teams from switching teams too quickly"""

    auto_balance_threshold: int = UnsetField
    """The difference in amount of players per team required for auto balance measures to be put in place"""
    auto_balance_enabled: bool = UnsetField
    """Whether the server will apply auto balance measures if necessary"""

    vote_kick_enabled: bool = UnsetField
    """Whether the server allows vote kicking"""

    chat_filter: set = UnsetField
    """The list of words that will get flagged by the server's chat filter"""
    chat_filter_enabled: bool = UnsetField
    """Whether the server has a chat filter enabled"""

#####################################
#              EVENTS               #
#####################################

class EventModel(InfoModel):
    __key_fields__ = ()
    event_time: datetime = None

    @pydantic.validator('event_time', pre=True, always=True)
    def set_ts_now(cls, v):
        return v or datetime.now(tz=timezone.utc)

class PlayerJoinServerEvent(EventModel):
    __scope_path__ = 'events.player_join_server'
    player: Union[Player, Link] = UnsetField

class ServerMapChangedEvent(EventModel):
    __scope_path__ = 'events.server_map_changed'
    old: str = UnsetField
    new: str = UnsetField

class ServerMatchStartedEvent(EventModel):
    __scope_path__ = 'events.server_match_started'
    map: str = UnsetField

class ServerWarmupEndedEvent(EventModel):
    __scope_path__ = 'events.server_warmup_ended'

class ServerMatchEndedEvent(EventModel):
    __scope_path__ = 'events.server_match_ended'
    map: str = UnsetField
    score: str = UnsetField

class SquadCreatedEvent(EventModel):
    __scope_path__ = 'events.squad_created'
    squad: Union[Squad, Link] = UnsetField

class PlayerSwitchTeamEvent(EventModel):
    __scope_path__ = 'events.player_switch_team'
    player: Union[Player, Link] = UnsetField
    old: Union[Team, Link, None] = UnsetField
    new: Union[Team, Link, None] = UnsetField

class PlayerSwitchSquadEvent(EventModel):
    __scope_path__ = 'events.player_switch_squad'
    player: Union[Player, Link] = UnsetField
    old: Union[Squad, Link, None] = UnsetField
    new: Union[Squad, Link, None] = UnsetField

class SquadLeaderChangeEvent(EventModel):
    __scope_path__ = 'events.squad_leader_change'
    squad: Union[Squad, Link] = UnsetField
    old: Union[Player, Link, None] = UnsetField
    new: Union[Player, Link, None] = UnsetField

class PlayerChangeRoleEvent(EventModel):
    __scope_path__ = 'events.player_change_role'
    player: Union[Player, Link] = UnsetField
    old: Union[str, None] = UnsetField
    new: Union[str, None] = UnsetField

class PlayerChangeLoadoutEvent(EventModel):
    __scope_path__ = 'events.player_change_loadout'
    player: Union[Player, Link] = UnsetField
    old: Union[str, None] = UnsetField
    new: Union[str, None] = UnsetField

class PlayerEnterAdminCamEvent(EventModel):
    __scope_path__ = 'events.player_enter_admin_cam'
    player: Union[Player, Link] = UnsetField

class PlayerMessageEvent(EventModel):
    __scope_path__ = 'events.player_message'
    player: Union[Player, Link, str] = UnsetField
    message: str = UnsetField
    channel: Any = UnsetField

class PlayerKillEvent(EventModel):
    __scope_path__ = 'events.player_kill'
    player: Union[Player, Link, str] = UnsetField
    other: Union[Player, Link, None] = UnsetField
    weapon: str = UnsetField

class PlayerTeamkillEvent(PlayerKillEvent):
    __scope_path__ = 'events.player_teamkill'

class PlayerSuicideEvent(EventModel):
    __scope_path__ = 'events.player_suicide'
    player: Union[Player, Link, str] = UnsetField

class ObjectiveCaptureEvent(EventModel):
    __scope_path__ = 'events.objective_capture'
    team: Union[Team, Link] = UnsetField
    score: str = UnsetField

class PlayerLevelUpEvent(EventModel):
    __scope_path__ = 'events.player_level_up'
    player: Union[Player, Link] = UnsetField
    old: int = UnsetField
    new: int = UnsetField

class PlayerScoreUpdateEvent(EventModel):
    __scope_path__ = 'events.player_score_update'
    player: Union[Player, Link] = UnsetField

class PlayerExitAdminCamEvent(EventModel):
    __scope_path__ = 'events.player_exit_admin_cam'
    player: Union[Player, Link] = UnsetField

class PlayerLeaveServerEvent(EventModel):
    __scope_path__ = 'events.player_leave_server'
    player: Union[Player, Link] = UnsetField

class SquadDisbandedEvent(EventModel):
    __scope_path__ = 'events.squad_disbanded'
    squad: Union[Squad, Link] = UnsetField

class PrivateEventModel(EventModel):
    """A special event model that simply flags
    this event as one that should not be adopted
    by info trees."""

class ActivationEvent(PrivateEventModel):
    __scope_path__ = 'events.activation'
class IterationEvent(PrivateEventModel):
    __scope_path__ = 'events.iteration'
class DeactivationEvent(PrivateEventModel):
    __scope_path__ = 'events.deactivation'

#####################################

@unique
class EventTypes(Enum):

    def __str__(self):
        return self.name

    activation = ActivationEvent
    iteration = IterationEvent
    deactivation = DeactivationEvent

    # In order of evaluation!
    player_join_server = PlayerJoinServerEvent
    server_map_changed = ServerMapChangedEvent
    server_match_started = ServerMatchStartedEvent
    server_warmup_ended = ServerWarmupEndedEvent
    server_match_ended = ServerMatchEndedEvent
    squad_created = SquadCreatedEvent
    player_switch_team = PlayerSwitchTeamEvent
    player_switch_squad = PlayerSwitchSquadEvent
    squad_leader_change = SquadLeaderChangeEvent
    player_change_role = PlayerChangeRoleEvent
    player_change_loadout = PlayerChangeLoadoutEvent
    player_enter_admin_cam = PlayerEnterAdminCamEvent
    player_message = PlayerMessageEvent
    player_kill = PlayerKillEvent
    player_teamkill = PlayerTeamkillEvent
    player_suicide = PlayerSuicideEvent
    objective_capture = ObjectiveCaptureEvent
    player_level_up = PlayerLevelUpEvent
    player_score_update = PlayerScoreUpdateEvent
    player_exit_admin_cam = PlayerExitAdminCamEvent
    player_leave_server = PlayerLeaveServerEvent
    squad_disbanded = SquadDisbandedEvent

    @classmethod
    def _missing_(cls, value):
        try:
            return cls[value]
        except KeyError:
            return super()._missing_(value)

    @classmethod
    def all(cls):
        """An iterator containing all events, including private ones."""
        return (cls._member_map_[name] for name in cls._member_names_)
    @classmethod
    def public(cls):
        """An iterator containing all events, excluding private ones."""
        return (cls._member_map_[name] for name in cls._member_names_ if not issubclass(cls._member_map_[name].value, PrivateEventModel))

#Events = pydantic.create_model('Events', __base__=InfoModel, **{event.name: (List[event.value], Unset) for event in EventTypes.public()})
class Events(InfoModel):
    player_join_server: List['PlayerJoinServerEvent'] = UnsetField
    server_map_changed: List['ServerMapChangedEvent'] = UnsetField
    server_match_started: List['ServerMatchStartedEvent'] = UnsetField
    server_warmup_ended: List['ServerWarmupEndedEvent'] = UnsetField
    squad_created: List['SquadCreatedEvent'] = UnsetField
    player_switch_team: List['PlayerSwitchTeamEvent'] = UnsetField
    player_switch_squad: List['PlayerSwitchSquadEvent'] = UnsetField
    squad_leader_change: List['SquadLeaderChangeEvent'] = UnsetField
    player_change_role: List['PlayerChangeRoleEvent'] = UnsetField
    player_change_loadout: List['PlayerChangeLoadoutEvent'] = UnsetField
    player_enter_admin_cam: List['PlayerEnterAdminCamEvent'] = UnsetField
    player_message: List['PlayerMessageEvent'] = UnsetField
    player_kill: List['PlayerKillEvent'] = UnsetField
    player_teamkill: List['PlayerTeamkillEvent'] = UnsetField
    player_suicide: List['PlayerSuicideEvent'] = UnsetField
    objective_capture: List['ObjectiveCaptureEvent'] = UnsetField
    server_match_ended: List['ServerMatchEndedEvent'] = UnsetField
    player_level_up: List['PlayerLevelUpEvent'] = UnsetField
    player_score_update: List['PlayerScoreUpdateEvent'] = UnsetField
    player_exit_admin_cam: List['PlayerExitAdminCamEvent'] = UnsetField
    player_leave_server: List['PlayerLeaveServerEvent'] = UnsetField
    squad_disbanded: List['SquadDisbandedEvent'] = UnsetField

    def __getitem__(self, key) -> List[InfoModel]:
        return obj_getattr(self, str(EventTypes(key)))
    def __setitem__(self, key, value):
        setattr(self, str(EventTypes(key)), value)

    def add(self, *events: Union[EventModel, type[EventModel]]):
        """Populate this model with events.

        Events are placed in the right attribute automatically. If
        still `Unset` they will be initialized. Note that private
        event models cannot be added.

        Passing an event class instead of an object will initialize
        the corresponding property. This will prevent this property
        from be overwritten when merging or when automatically
        compiling events.

        Parameters
        ----------
        *events : Union[EventModel, type[EventModel]]
            The events to add and event types to initialize
        """
        for event in events:
            if isclass(event):
                if not issubclass(event, EventModel) or issubclass(event, PrivateEventModel):
                    raise ValueError("%s is a subclass of PrivateEventModel or is not an event")
                etype = EventTypes(event)
                if self[etype] is Unset:
                    self[etype] = InfoModelArray()
            else:
                if not isinstance(event, EventModel) or isinstance(event, PrivateEventModel):
                    raise ValueError("%s is of type PrivateEventModel or is not an event model")
                etype = EventTypes(event.__class__)
                if self[etype] is Unset:
                    self[etype] = InfoModelArray([event])
                else:
                    self[etype].append(event)

# ----- Info Hopper -----

class InfoHopper(ModelTree):
    players: List['Player'] = UnsetField
    squads: List['Squad'] = UnsetField
    teams: List['Team'] = UnsetField
    server: 'Server' = None
    events: 'Events' = None
    __solid__: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.server:
            self.server = Server(self)
        if not self.events:
            self.events = Events(self)
        obj_setattr(self, '__solid__', not self.__config__.allow_mutation)

    def __getattribute__(self, name: str):
        if name in obj_getattr(self, '__fields__'):
            res = super().__getattribute__(name)
            if res is Unset:
                raise AttributeError(name)
            return res
        else:
            return super().__getattribute__(name)

    def add_players(self, *players: 'Player'):
        self._add('players', *players)
    def add_squads(self, *squads: 'Squad'):
        self._add('squads', *squads)
    def add_teams(self, *teams: 'Team'):
        self._add('teams', *teams)
    def set_server(self, server: 'Server'):
        self.server = server

    def find_players(self, single=False, ignore_unknown=False, **filters) -> Union['Player', List['Player'], None]:
        return self._get('players', multiple=not single, ignore_unknown=ignore_unknown, **filters)
    def find_squads(self, single=False, ignore_unknown=False, **filters) -> Union['Squad', List['Squad'], None]:
        return self._get('squads', multiple=not single, ignore_unknown=ignore_unknown, **filters)
    def find_teams(self, single=False, ignore_unknown=False, **filters) -> Union['Team', List['Team'], None]:
        return self._get('teams', multiple=not single, ignore_unknown=ignore_unknown, **filters)

    @property
    def team1(self):
        return self.teams[0]
    @property
    def team2(self):
        return self.teams[1]

    @classmethod
    def gather(cls, *infos: 'InfoHopper'):
        """Gathers and combines all :class:`InfoHopper`s
        and returns a new hopper"""
        info = cls()
        for other in infos:
            if not other:
                continue
            info.merge(other)
        return info

    def compare_older(self, other: 'InfoHopper', event_time: datetime = None):
        events = Events(self)

        # Since this method should only be used once done with
        # combining data from all sources, and events are never
        # really referenced backwards, it is completely safe to
        # pass objects directly. Much more reliable than Links.

        if not event_time:
            event_time = datetime.now(tz=timezone.utc)

        if self.has('players') and other.has('players'):
            others = InfoModelArray(other.players)
            for player in self.players:
                match = self._get(others, multiple=False, ignore_unknown=True, **player.get_key_attributes())
                if match:
                    del others[others.index(match)]

                    # Role Change Event

                    if player.has('role') and match.has('role'):
                        if player.role != match.role:
                            events.add(PlayerChangeRoleEvent(self, event_time=event_time, player=player.create_link(with_fallback=True), old=match.role, new=player.role))

                    # Loadout Change Event

                    """
                    if player.has('loadout') and match.has('loadout'):
                        if player.loadout != match.loadout:
                            events.add(PlayerChangeLoadoutEvent(self, event_time=event_time, player=player.create_link(with_fallback=True), old=match.loadout, new=player.loadout))
                    """

                    # Level Up Event

                    if player.has('level') and match.has('level'):
                        # Sometimes it takes the server a little to load the player's actual level. Here's an attempt
                        # to prevent a levelup event from occurring during those instances.
                        if player.level > match.level and not (match.level == 1 and player.level - match.level > 1):
                            events.add(PlayerLevelUpEvent(self, event_time=event_time, player=player.create_link(with_fallback=True), old=match.level, new=player.level))

                if not player.get('joined_at'):
                    if match:
                        player.joined_at = match.get('joined_at') or player.__created_at__
                    else:
                        player.joined_at = player.__created_at__

                if not match:
                    events.add(PlayerJoinServerEvent(self, event_time=event_time, player=player.create_link(with_fallback=True)))

                p_squad = player.get('squad')
                m_squad = match.get('squad') if match else None
                if p_squad != m_squad:
                    events.add(PlayerSwitchSquadEvent(self, event_time=event_time,
                        player=player.create_link(with_fallback=True, hopper=self),
                        old=m_squad.create_link(with_fallback=True, hopper=self) if m_squad else None,
                        new=p_squad.create_link(with_fallback=True, hopper=self) if p_squad else None,
                    ))

                p_team = player.get('team')
                m_team = match.get('team') if match else None
                if p_team != m_team:
                    events.add(PlayerSwitchTeamEvent(self, event_time=event_time,
                        player=player.create_link(with_fallback=True, hopper=self),
                        old=m_team.create_link(with_fallback=True) if m_team else None,
                        new=p_team.create_link(with_fallback=True) if p_team else None,
                    ))

            for player in others:
                if other.server.state == "in_progress":
                    events.add(PlayerScoreUpdateEvent(self, event_time=event_time,
                        player=player.create_link(with_fallback=True, hopper=self)
                    ))

                events.add(PlayerLeaveServerEvent(self, event_time=event_time,
                    player=player.create_link(with_fallback=True, hopper=self)
                ))
                if player.get('squad'):
                    events.add(PlayerSwitchSquadEvent(self, event_time=event_time,
                        player=player.create_link(with_fallback=True, hopper=self),
                        old=player.squad.create_link(with_fallback=True, hopper=self),
                        new=None
                    ))
                if player.get('team'):
                    events.add(PlayerSwitchTeamEvent(self, event_time=event_time,
                        player=player.create_link(with_fallback=True, hopper=self),
                        old=player.team.create_link(with_fallback=True),
                        new=None
                    ))

        if self.has('squads') and other.has('squads'):
            others = InfoModelArray(other.squads)
            for squad in self.squads:
                match = self._get(others, multiple=False, ignore_unknown=True, **squad.get_key_attributes())
                if match:
                    del others[others.index(match)]

                    # Squad Leader Change Event

                    if squad.has('leader') and match.has('leader'):
                        if squad.leader != match.leader:
                            old = match.leader.create_link(with_fallback=True, hopper=self) if match.leader else None
                            new = squad.leader.create_link(with_fallback=True, hopper=self) if squad.leader else None
                            events.add(SquadLeaderChangeEvent(self, event_time=event_time, squad=squad.create_link(with_fallback=True), old=old, new=new))

                if not squad.get('created_at'):
                    if match:
                        squad.created_at = match.get('created_at') or squad.__created_at__
                    else:
                        squad.created_at = squad.__created_at__

                if not match:
                    events.add(SquadCreatedEvent(self, event_time=event_time, squad=squad.create_link(with_fallback=True)))

            for squad in others:
                events.add(SquadDisbandedEvent(self, event_time=event_time, squad=squad.create_link(with_fallback=True, hopper=self)))

        if self.has('teams') and other.has('teams'):
            others = InfoModelArray(other.teams)
            for team in self.teams:
                match = self._get(others, multiple=False, ignore_unknown=True, **team.get_key_attributes())
                if match:
                    del others[others.index(match)]

                # Objective Capture Event

                if team.has('score') and match.has('score') and self.server.get('state') != 'warmup':
                    if team.score > match.score:
                        if team.id == 1:
                            message = f"{team.score} - {5 - team.score}"
                        else:
                            message = f"{5 - team.score} - {team.score}"
                        events.add(ObjectiveCaptureEvent(self, event_time=event_time, team=team.create_link(with_fallback=True), score=message))

                if not team.get('created_at'):
                    if match:
                        team.created_at = match.get('created_at') or team.__created_at__
                    else:
                        team.created_at = team.__created_at__

        self_map = self.server.get('map')
        other_map = other.server.get('map')
        if all([self_map, other_map]) and self_map != other_map:
            events.add(ServerMapChangedEvent(self, event_time=event_time, old=other_map, new=self_map))

        self.events.merge(events)



# discord.py provides some nice tools for making flags. We have to be
# careful for breaking changes however.

@fill_with_flags()
class EventFlags(Flags):

    @classmethod
    def connections(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_join_server = True
        self.player_leave_server = True
        return self

    @classmethod
    def game_states(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.server_map_changed = True
        self.server_match_started = True
        self.server_warmup_ended = True
        self.server_match_ended = True
        self.objective_capture = True
        return self

    @classmethod
    def teams(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_switch_team = True
        return self

    @classmethod
    def squads(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_switch_squad = True
        self.squad_created = True
        self.squad_disbanded = True
        self.squad_leader_change = True
        return self

    @classmethod
    def deaths(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_kill = True
        self.player_teamkill = True
        self.player_suicide = True
        return self

    @classmethod
    def messages(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_message = True
        return self

    @classmethod
    def admin_cam(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_enter_admin_cam = True
        self.player_exit_admin_cam = True
        return self

    @classmethod
    def roles(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_change_role = True
        self.player_change_loadout = True
        self.player_level_up = True
        return self

    @classmethod
    def scores(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.player_score_update = True
        return self

    @classmethod
    def modifiers(cls: type['EventFlags']) -> 'EventFlags':
        self = cls.none()
        self.rule_violated = True
        self.arty_assigned = True
        self.arty_unassigned = True
        self.start_arty_cooldown = True
        self.cancel_arty_cooldown = True
        self.player_kicked = True
        return self


    @flag_value
    def player_join_server(self):
        return 1 << 0

    @flag_value
    def server_map_changed(self):
        return 1 << 1

    @flag_value
    def server_match_started(self):
        return 1 << 2

    @flag_value
    def server_warmup_ended(self):
        return 1 << 3

    @flag_value
    def server_match_ended(self):
        return 1 << 4

    @flag_value
    def squad_created(self):
        return 1 << 5

    @flag_value
    def player_switch_team(self):
        return 1 << 6

    @flag_value
    def player_switch_squad(self):
        return 1 << 7

    @flag_value
    def squad_leader_change(self):
        return 1 << 8

    @flag_value
    def player_change_role(self):
        return 1 << 9

    @flag_value
    def player_change_loadout(self):
        return 1 << 10

    @flag_value
    def player_enter_admin_cam(self):
        return 1 << 11

    @flag_value
    def player_message(self):
        return 1 << 12

    @flag_value
    def player_kill(self):
        return 1 << 13

    @flag_value
    def player_teamkill(self):
        return 1 << 14

    @flag_value
    def player_suicide(self):
        return 1 << 15

    @flag_value
    def player_level_up(self):
        return 1 << 16

    @flag_value
    def player_exit_admin_cam(self):
        return 1 << 17

    @flag_value
    def player_leave_server(self):
        return 1 << 18

    @flag_value
    def squad_disbanded(self):
        return 1 << 19

    @flag_value
    def objective_capture(self):
        return 1 << 20

    @flag_value
    def rule_violated(self):
        return 1 << 21

    @flag_value
    def arty_assigned(self):
        return 1 << 22

    @flag_value
    def arty_unassigned(self):
        return 1 << 23

    @flag_value
    def start_arty_cooldown(self):
        return 1 << 24

    @flag_value
    def cancel_arty_cooldown(self):
        return 1 << 25

    @flag_value
    def player_score_update(self):
        return 1 << 26

    @flag_value
    def player_kicked(self):
        return 1 << 27


    def filter_logs(self, logs: Sequence['LogLine']):
        allowed_types = {type_ for type_, allowed in self if allowed}
        for log in logs:
            if log.type in allowed_types:
                yield log
