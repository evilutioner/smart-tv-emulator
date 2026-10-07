"""python-roku against the Roku emulator, through the library's public API only.

A synchronous `requests` client and one of the oldest Roku libraries: device-info and app
queries, every remote key by attribute name, `literal()` text, launching an app or its store
page, icons, search, and the touch and motion-sensor input that rides on `POST /input`.
"""
from roku import Roku

from tvemu_binding import Harness

# python-roku's attribute for each navigation key, and the ECP key it sends.
KEYS = {"home": "Home", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "select": "Select", "back": "Back", "play": "Play", "reverse": "Rev",
        "forward": "Fwd", "replay": "InstantReplay", "info": "Info",
        "backspace": "Backspace", "enter": "Enter"}
TEXT = "tvemu42"


async def main(harness: Harness) -> None:
    roku = Roku(harness.device_host, port=harness.device_port, timeout=5)

    async with harness.step("device-info and the app list", "identify", required=True):
        info = roku.device_info
        expected = (await harness.state())["device"]
        assert info.model_num == expected["model_number"], info.model_num
        # python-roku joins software-version and software-build into one dotted string.
        assert info.software_version.startswith(expected["software_version"] + "."), \
            info.software_version
        apps = roku.apps
        assert apps, "no applications parsed"

    is_tv = info.roku_type == "TV"
    app = next(item for item in apps if not item.id.startswith("tvinput"))

    async with harness.step("active app, power state and channels", "query-state"):
        assert roku.active_app is not None, "no active application parsed"
        assert roku.current_app is not None, "no current application parsed"
        assert roku.power_state == "On", roku.power_state
        if is_tv:
            assert isinstance(roku.tv_channels, list)

    async with harness.step("navigation and playback keys", "key"):
        for name, key in KEYS.items():
            before = (await harness.state())["counts"].get(key, 0)
            getattr(roku, name)()
            await harness.wait(lambda state: state["counts"].get(key, 0) == before + 1,
                               f"{key} counted")

    async with harness.step(f"literal text {TEXT!r}", "text"):
        since = await harness.last_event_id()
        roku.literal(TEXT)
        arrived = [event["operation"] for event in await harness.events(since)
                   if event.get("kind") == "command" and event.get("status") == 200]
        assert arrived == [f"keypress/Lit_{char}" for char in TEXT], arrived

    async with harness.step("volume up, down and mute", "volume"):
        for name, key in (("volume_up", "VolumeUp"), ("volume_down", "VolumeDown"),
                          ("volume_mute", "VolumeMute")):
            before = (await harness.state())["counts"].get(key, 0)
            getattr(roku, name)()
            await harness.wait(lambda state: state["counts"].get(key, 0) == before + 1,
                               f"{key} counted")

    async with harness.step("power off and on", "power"):
        roku.poweroff()
        await harness.wait(lambda state: state["power"] is False, "power off")
        roku.poweron()
        await harness.wait(lambda state: state["power"] is True, "power on")

    async with harness.step("standby reported by device-info", "query-state"):
        roku.poweroff()
        await harness.wait(lambda state: state["power"] is False, "power off")
        try:
            assert roku.power_state == "Off", roku.power_state
        finally:
            roku.poweron()

    async with harness.step("launch an installed application", "launch"):
        since = await harness.last_event_id()
        app.launch()
        launches = [event for event in await harness.events(since)
                    if event.get("kind") == "application"]
        assert launches and launches[-1]["status"] == 200, launches

    async with harness.step("open an application's store page", "launch"):
        since = await harness.last_event_id()
        app.store()
        launches = [event for event in await harness.events(since)
                    if event.get("kind") == "application"]
        assert launches and launches[-1]["status"] == 200, launches

    async with harness.step("an application's icon", "query-state"):
        assert roku.icon(app), "empty icon"

    async with harness.step("search for a keyword", "search"):
        roku.search(keyword="tvemu")

    async with harness.step("a touch at a point", "pointer"):
        roku.touch(10, 20)

    async with harness.step("motion-sensor input", "pointer"):
        roku.orientation(1, 2, 3)


Harness.main(main)
