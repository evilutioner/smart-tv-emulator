"""rokuecp against the Roku emulator, through the library's public API only.

Each step uses what Home Assistant's Roku integration uses: `update()` for identity and
state, `remote()` for keys, `literal()` for text, `launch()`/`tune()` for applications, and
`search()`/`play_on_roku()`, which ask for requests no Roku capture holds.
"""
from rokuecp import Roku
from rokuecp.const import VALID_REMOTE_KEYS

from tvemu_binding import Harness

# rokuecp's own names for the navigation keys, and the ECP key each one sends.
KEYS = {"home": "Home", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "select": "Select", "back": "Back", "play": "Play", "reverse": "Rev",
        "forward": "Fwd", "replay": "InstantReplay", "info": "Info",
        "backspace": "Backspace", "enter": "Enter"}
TEXT = "tvemu42"
VOLUME = ("VolumeUp", "VolumeDown", "VolumeMute")
POWER = ("Power", "PowerOff", "PowerOn", "Sleep")


async def offers(harness: Harness) -> None:
    """What rokuecp can do, read from rokuecp wherever it publishes it."""
    keys = set(VALID_REMOTE_KEYS.values())
    harness.offers("keys", keys - set(VOLUME) - set(POWER))
    harness.offers("volume", keys & set(VOLUME))
    harness.offers("power", keys & set(POWER))
    harness.offers("text", ["letters", "digits", "space", "punctuation", "non-ASCII"])
    harness.offers("auth", ["refused in Limited mode", "refused in Disabled mode"])
    harness.offers("apps", ["launch", "tune", "search", "play_on_roku"])


async def main(harness: Harness) -> None:
    await offers(harness)
    async with Roku(harness.device_host, port=harness.device_port) as roku:
        async with harness.step("device-info, apps and channels", "identify", required=True,
                                covers=["model_number", "version"]):
            device = await roku.update(full_update=True)
            harness.offers("identity", Harness.names(device.info))
            # What update() fills besides identity: the device's state, one field each.
            harness.offers("state", [name for name in Harness.names(device)
                                     if name not in ("info", "apps")])
            expected = (await harness.state())["device"]
            assert device.info.model_number == expected["model_number"], device.info.model_number
            assert device.info.version == expected["software_version"], device.info.version
            assert device.apps, "no applications parsed"

        is_tv = device.info.device_type == "tv"

        async with harness.step("active app, media and channel state", "query-state",
                                covers=["app", "media", *(["channels"] if is_tv else [])]):
            since = await harness.last_event_id()
            device = await roku.update(full_update=True)
            assert device.app is not None, "no active application parsed"
            assert device.state.standby is False
            asked = {event["operation"] for event in await harness.events(since)
                     if event.get("kind") == "query" and event.get("status") == 200}
            # A Roku TV is asked for its channel list too; an empty list is a fair answer.
            assert ("query/tv-channels" in asked) == is_tv, sorted(asked)

        async with harness.step("navigation and playback keys", "key", covers=KEYS.values()):
            for name, key in KEYS.items():
                before = (await harness.state())["counts"].get(key, 0)
                await roku.remote(name)
                await harness.wait(lambda state: state["counts"].get(key, 0) == before + 1,
                                   f"{key} counted")

        if device.info.supports_find_remote:
            async with harness.step("find remote", "key", covers=["FindRemote"]):
                await roku.remote("find_remote")
                await harness.wait(lambda state: state["counts"].get("FindRemote", 0) >= 1,
                                   "FindRemote counted")

        async with harness.step(f"literal text {TEXT!r}", "text", covers=["letters", "digits"]):
            since = await harness.last_event_id()
            await roku.literal(TEXT)
            arrived = [event["operation"] for event in await harness.events(since)
                       if event.get("kind") == "command" and event.get("status") == 200]
            assert arrived == [f"keypress/Lit_{char}" for char in TEXT], arrived

        async with harness.step("volume up, down and mute", "volume", covers=VOLUME):
            for name, key in (("volume_up", "VolumeUp"), ("volume_down", "VolumeDown"),
                              ("volume_mute", "VolumeMute")):
                before = (await harness.state())["counts"].get(key, 0)
                await roku.remote(name)
                await harness.wait(lambda state: state["counts"].get(key, 0) == before + 1,
                                   f"{key} counted")

        async with harness.step("power off and on", "power", covers=["PowerOff", "PowerOn"]):
            await roku.remote("poweroff")
            await harness.wait(lambda state: state["power"] is False, "power off")
            await roku.remote("poweron")
            await harness.wait(lambda state: state["power"] is True, "power on")

        async with harness.step("standby reported by device-info", "query-state",
                                covers=["state"]):
            await roku.remote("poweroff")
            await harness.wait(lambda state: state["power"] is False, "power off")
            try:
                assert (await roku.update()).state.standby is True, "standby not parsed"
            finally:
                await roku.remote("poweron")

        async with harness.step("launch an application with a deep link", "launch",
                                covers=["launch"]):
            since = await harness.last_event_id()
            await roku.launch("12", {"contentId": "tvemu-1", "mediaType": "movie"})
            launches = [event for event in await harness.events(since)
                        if event.get("kind") == "application"]
            assert launches and launches[-1]["status"] == 200, launches

        if is_tv:
            async with harness.step("tune a broadcast channel", "launch", covers=["tune"]):
                since = await harness.last_event_id()
                await roku.tune("1.1")
                launches = [event for event in await harness.events(since)
                            if event.get("kind") == "application"]
                assert launches and launches[-1]["status"] == 200, launches

        async with harness.step("search for a keyword", "search", covers=["search"]):
            await roku.search("tvemu")

        async with harness.step("play a URL on the device", "cast", covers=["play_on_roku"]):
            await roku.play_on_roku("http://example.test/video.mp4")


Harness.main(main)
