import asyncio
from collections import Counter
from typing import Mapping

import aiohttp

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.commands import Cog
from redbot.core.data_manager import cog_data_path

from ..utils import PlaylistScope
from . import abc, cog_utils, commands, events, tasks, utilities
from .cog_utils import CompositeMetaClass


class Audio(
    commands.Commands,
    events.Events,
    tasks.Tasks,
    utilities.Utilities,
    Cog,
    metaclass=CompositeMetaClass,
):
    """Class joining all Audio subclasses"""

    _default_lavalink_settings = {
        "host": "localhost",
        "rest_port": 2333,
        "ws_port": 2333,
        "password": "youshallnotpass",
    }

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 2711759130, force_registration=True)

        self.api_interface = None
        self.player_manager = None
        self.playlist_api = None
        self.local_folder_current_path = cog_data_path(raw_name="Audio") / "localtracks"
        self.db_conn = None
        self.session = aiohttp.ClientSession()

        self._error_counter = Counter()
        self._error_timer = {}
        self._disconnected_players = {}
        self.skip_votes = {}
        self.play_lock = {}
        self._daily_playlist_cache = {}
        self._dj_status_cache = {}
        self._dj_role_cache = {}

        self.lavalink_connect_task = None
        self.player_automated_timer_task = None
        self.cog_cleaned_up = False
        self.lavalink_connection_aborted = False
        self.api_interface = None
        self.lavalink_connect_task = None
        self.player_automated_timer_task = None

        default_global = dict(
            schema_version=1,
            cache_level=0,
            cache_age=365,
            global_db_enabled=False,
            global_db_get_timeout=5,  # Here as a placeholder in case we want to enable the command
            status=False,
            use_external_lavalink=False,
            restrict=True,
            localpath=str(cog_data_path(raw_name="Audio")),
            url_keyword_blacklist=[],
            url_keyword_whitelist=[],
            **self._default_lavalink_settings,
        )

        default_guild = dict(
            auto_play=False,
            autoplaylist={"enabled": False, "id": None, "name": None, "scope": None},
            disconnect=False,
            dj_enabled=False,
            dj_role=None,
            daily_playlists=False,
            emptydc_enabled=False,
            emptydc_timer=0,
            emptypause_enabled=False,
            emptypause_timer=0,
            jukebox=False,
            jukebox_price=0,
            maxlength=0,
            notify=False,
            repeat=False,
            shuffle=False,
            shuffle_bumped=True,
            thumbnail=False,
            volume=100,
            vote_enabled=False,
            vote_percent=0,
            room_lock=None,
            url_keyword_blacklist=[],
            url_keyword_whitelist=[],
        )
        _playlist: Mapping = dict(id=None, author=None, name=None, playlist_url=None, tracks=[])

        self.config.init_custom("EQUALIZER", 1)
        self.config.register_custom("EQUALIZER", eq_bands=[], eq_presets={})
        self.config.init_custom(PlaylistScope.GLOBAL.value, 1)
        self.config.register_custom(PlaylistScope.GLOBAL.value, **_playlist)
        self.config.init_custom(PlaylistScope.GUILD.value, 2)
        self.config.register_custom(PlaylistScope.GUILD.value, **_playlist)
        self.config.init_custom(PlaylistScope.USER.value, 2)
        self.config.register_custom(PlaylistScope.USER.value, **_playlist)
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        # These has to be a task since this requires the bot to be ready
        # If it waits for ready in startup, we cause a deadlock during initial load
        # as initial load happens before the bot can ever be ready.
        self.cog_init_task = self.bot.loop.create_task(self.initialize())
        self.cog_ready_event = asyncio.Event()