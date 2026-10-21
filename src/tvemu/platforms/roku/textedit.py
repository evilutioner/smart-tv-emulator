"""Measured native textedit sessions, backed by the shared device text buffer."""
from __future__ import annotations

import json
from tvemu.platforms.common.jsonbytes import replace_json_value


class TextEdit:
    def __init__(self, core, profile, notify):
        self.core, self.profile, self.notify = core, profile, notify
        self.number = 0
        self.opened = False
        self.last = None

    def config(self):
        return self.profile().runtime.get("textedit", {}).get("native", {})

    def details(self):
        config, field = self.config(), self.core.text_field
        if not config or not field.focused:
            return {"textedit-id": "none"}
        cursor = field.cursor if field.cursor is not None else len(field.text)
        return {"masked": "true" if self.core.masked() else "false",
                "max-length": str(config["max_length"]),
                "selection-start": str(cursor), "selection-end": str(cursor),
                "text": field.text, "textedit-id": str(self.number),
                "textedit-type": config["type"]}

    def observe(self):
        if not self.config():
            self.opened, self.last = False, None
            return
        focused = self.core.text_field.focused
        if focused and not self.opened:
            self.number += 1
            self.core.text_field.cursor = 0
            self.opened = True
            self.last = self.details()
            self.notify("textedit-opened", self.last)
        elif not focused and self.opened:
            self.notify("textedit-closed", {"textedit-id": str(self.number)})
            self.opened, self.last = False, None
        elif focused:
            details = self.details()
            if details != self.last:
                self.last = details
                self.notify("textedit-changed", details)

    def document(self):
        profile = self.profile()
        if not self.core.text_field.focused:
            return profile.ecp2_documents["query-textedit-state"][0]
        body = profile.native_text_document
        for key, value in self.details().items():
            body = replace_json_value(body, "textedit-state." + key,
                                      json.dumps(value, ensure_ascii=True).encode())
        return body

    async def write(self, data, peer):
        valid = isinstance(data.get("param-textedit-id"), str) and isinstance(data.get("param-text"), str)
        if not valid:
            return 400
        field, config = self.core.text_field, self.config()
        text = data["param-text"]
        if (not config or not field.focused or data["param-textedit-id"] != str(self.number)
                or len(text) > config["max_length"]):
            # The measured set answers 200 and leaves text/caret unchanged in these cases.
            return 200
        try:
            cursor = int(data.get("param-selection-end", len(text)))
        except (ValueError, TypeError):
            cursor = 0
        status, _ = await self.core.text("insert", text=text, replace=True,
                                         cursor=cursor, transport="ws", peer=peer)
        return status
