import urllib.parse
import urllib.request

from led import config
from led.Interfaces.EventTarget import EventTarget


class TelegramTarget(EventTarget):
    name = "TelegramTarget"

    def __init__(self):
        super().__init__()
        cfg = config.get('targets')[self.name]
        self.bot_token = cfg['bot_token']
        self.chat_id = cfg['chat_id']

    def _send(self, source, message):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': self.chat_id,
            'text': message,
        }).encode('utf-8')
        request = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
