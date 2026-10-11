"""python-roku against the Roku emulator, through the library's public API only.

A synchronous `requests` client and one of the oldest Roku libraries: device-info and app
queries, every remote key by attribute name, `literal()` text, launching an app or its store
page, icons, search, and the touch and motion-sensor input that rides on `POST /input`.
"""
from roku import Roku
from roku.core import COMMANDS, SENSORS, TOUCH_OPS

from tvemu_binding import Harness

# python-roku's attribute for each navigation key, and the ECP key it sends.
KEYS = {"home": "Home", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "select": "Select", "back": "Back", "play": "Play", "reverse": "Rev",
        "forward": "Fwd", "replay": "InstantReplay", "info": "Info",
        "backspace": "Backspace", "enter": "Enter"}
TEXT = "tvemu42"
VOLUME = ("VolumeUp", "VolumeDown", "VolumeMute")
POWER = ("Power", "PowerOff", "PowerOn")


def offers(harness: Harness) -> None:
    """What python-roku can do, read from python-roku wherever it publishes it."""
    keys = set(COMMANDS.values()) - {"Lit"}          # `literal` is the text API, not a key
    harness.offers("keys", keys - set(VOLUME) - set(POWER))
    harness.offers("volume", keys & set(VOLUME))
    harness.offers("power", keys & set(POWER))
    harness.offers("text", ["letters", "digits", "space", "punctuation", "non-ASCII"])
    harness.offers("pointer", [f"touch {op}" for op in TOUCH_OPS] + list(SENSORS))
    harness.offers("auth", ["refused in Limited mode", "refused in Disabled mode"])
    harness.offers("state", ["active_app", "current_app", "power_state", "tv_channels", "icon"])
    harness.offers("apps", ["launch", "store", "Channel.launch", "search"])
    harness.offers("discovery", ["discover"])


async def main(harness: Harness) -> None:
    roku = Roku(harness.device_host, port=harness.device_port, timeout=5)
    offers(harness)

    async with harness.step("device-info and the app list", "identify", required=True,
                            covers=["model_num", "software_version"]):
        info = roku.device_info
        harness.offers("identity", Harness.names(info))
        expected = (await harness.state())["device"]
        assert info.model_num == expected["model_number"], info.model_num
        # python-roku joins software-version and software-build into one dotted string.
        assert info.software_version.startswith(expected["software_version"] + "."), \
            info.software_version
        apps = roku.apps
        assert apps, "no applications parsed"

    is_tv = info.roku_type == "TV"
    app = next(item for item in apps if not item.id.startswith("tvinput"))

    async with harness.step("active app, power state and channels", "query-state",
                            covers=["active_app", "current_app", "power_state",
                                    *(["tv_channels"] if is_tv else [])]):
        assert roku.active_app is not None, "no active application parsed"
        assert roku.current_app is not None, "no current application parsed"
        assert roku.power_state == "On", roku.power_state
        if is_tv:
            assert isinstance(roku.tv_channels, list)

    async with harness.step("navigation and playback keys", "key", covers=KEYS.values()):
        for name, key in KEYS.items():
            before = (await harness.state())["counts"].get(key, 0)
            getattr(roku, name)()
            await harness.wait(lambda state: state["counts"].get(key, 0) == before + 1,
                               f"{key} counted")

    async with harness.step(f"literal text {TEXT!r}", "text", covers=["letters", "digits"]):
        since = await harness.last_event_id()
        roku.literal(TEXT)
        arrived = [event["operation"] for event in await harness.events(since)
                   if event.get("kind") == "command" and event.get("status") == 200]
        assert arrived == [f"keypress/Lit_{char}" for char in TEXT], arrived

    async with harness.step("volume up, down and mute", "volume", covers=VOLUME):
        for name, key in (("volume_up", "VolumeUp"), ("volume_down", "VolumeDown"),
                          ("volume_mute", "VolumeMute")):
            before = (await harness.state())["counts"].get(key, 0)
            getattr(roku, name)()
            await harness.wait(lambda state: state["counts"].get(key, 0) == before + 1,
                               f"{key} counted")

    async with harness.step("power off and on", "power", covers=["PowerOff", "PowerOn"]):
        roku.poweroff()
        await harness.wait(lambda state: state["power"] is False, "power off")
        roku.poweron()
        await harness.wait(lambda state: state["power"] is True, "power on")

    async with harness.step("standby reported by device-info", "query-state",
                            covers=["power_state"]):
        roku.poweroff()
        await harness.wait(lambda state: state["power"] is False, "power off")
        try:
            assert roku.power_state == "Off", roku.power_state
        finally:
            roku.poweron()

    async with harness.step("launch an installed application", "launch", covers=["launch"]):
        since = await harness.last_event_id()
        app.launch()
        launches = [event for event in await harness.events(since)
                    if event.get("kind") == "application"]
        assert launches and launches[-1]["status"] == 200, launches

    async with harness.step("open an application's store page", "launch", covers=["store"]):
        since = await harness.last_event_id()
        app.store()
        launches = [event for event in await harness.events(since)
                    if event.get("kind") == "application"]
        assert launches and launches[-1]["status"] == 200, launches

    async with harness.step("an application's icon", "query-state", covers=["icon"]):
        assert roku.icon(app), "empty icon"

    async with harness.step("search for a keyword", "search", covers=["search"]):
        roku.search(keyword="tvemu")

    async with harness.step("a touch at a point", "pointer", covers=["touch down"]):
        roku.touch(10, 20)

    async with harness.step("motion-sensor input", "pointer", covers=["orientation"]):
        roku.orientation(1, 2, 3)


Harness.main(main)
