import urllib.parse
import urllib.request

from led import config
from led.Interfaces.EventTarget import EventTarget


class TargetTelegram(EventTarget):
    name = "TargetTelegram"

    def __init__(self):
        super().__init__()
        cfg = config.get('targets')[self.name]
        self.bot_token = cfg.get('bot_token')
        chat_ids = cfg.get('chat_ids')
        if chat_ids is None and 'chat_id' in cfg:
            chat_ids = [cfg['chat_id']]
        self.chat_ids = list(chat_ids) if chat_ids else []

    def _initialize(self):
        if not self.bot_token or not isinstance(self.bot_token, str):
            raise ValueError(f"{self.name}: 'bot_token' is required and must be a string")
        if not self.chat_ids:
            raise ValueError(
                f"{self.name}: provide at least one recipient via 'chat_id' (string) "
                f"or 'chat_ids' (list of strings)"
            )
        for cid in self.chat_ids:
            if not isinstance(cid, (str, int)):
                raise ValueError(f"{self.name}: chat ids must be strings or integers, got {type(cid).__name__}")
        print(f"  {self.name}: {len(self.chat_ids)} chat id(s) configured")

    def _send(self, source, message):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        for chat_id in self.chat_ids:
            data = urllib.parse.urlencode({
                'chat_id': chat_id,
                'text': message,
            }).encode('utf-8')
            request = urllib.request.Request(url, data=data, method='POST')
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
