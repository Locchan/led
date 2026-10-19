import os

import requests

from led.Interfaces.EventTarget import EventTarget
from led.alerts import send_alert


# Extensions Telegram's sendPhoto / sendVideo accept as media.
PHOTO_FORMATS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')
VIDEO_FORMATS = ('.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v')


def _upload_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in PHOTO_FORMATS:
        return 'sendPhoto', 'photo'
    if ext in VIDEO_FORMATS:
        return 'sendVideo', 'video'
    return 'sendDocument', 'document'


def _api_error(resp):
    """Telegram's JSON error body, or None when this is not one.

    Timeouts and other transport failures never get here: requests raises
    before a response exists.
    """
    try:
        data = resp.json()
    except ValueError:
        return None
    if isinstance(data, dict) and data.get('ok') is False:
        return data.get('description') or 'Telegram API error'
    return None


class TargetTelegram(EventTarget):
    name = "TargetTelegram"

    def __init__(self, instance_id, cfg):
        super().__init__(instance_id)
        self.bot_token = cfg.get('bot_token')
        chat_ids = cfg.get('chat_ids')
        if chat_ids is None and 'chat_id' in cfg:
            chat_ids = [cfg['chat_id']]
        self.chat_ids = list(chat_ids) if chat_ids else []
        self._initialize()

    def _initialize(self):
        if not self.bot_token or not isinstance(self.bot_token, str):
            raise ValueError(f"[{self.id}] {self.name}: 'bot_token' is required and must be a string")
        if not self.chat_ids:
            raise ValueError(
                f"[{self.id}] {self.name}: provide at least one recipient via 'chat_id' (string) "
                f"or 'chat_ids' (list of strings)"
            )
        for cid in self.chat_ids:
            if not isinstance(cid, (str, int)):
                raise ValueError(
                    f"[{self.id}] {self.name}: chat ids must be strings or integers, got {type(cid).__name__}"
                )
        print(f"  [{self.id}] {self.name}: {len(self.chat_ids)} chat id(s) configured")

    def _send(self, source, message, files=None):
        for chat_id in self.chat_ids:
            if not files:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                requests.post(url, data=payload, timeout=10)
                continue

            for file_path in files:
                if not os.path.isfile(file_path):
                    continue
                method, field = _upload_for(file_path)
                url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
                with open(file_path, 'rb') as f:
                    payload = {
                        'chat_id': chat_id,
                        'caption': message,
                        'parse_mode': 'HTML'
                    }
                    if method == 'sendVideo':
                        payload['supports_streaming'] = 'true'
                    resp = requests.post(url, data=payload, files={field: f}, timeout=30)
                err = _api_error(resp)
                if not err:
                    continue
                send_alert(self, f"Failed to send {file_path}: {err}")
                try:
                    os.remove(file_path)
                except OSError as e:
                    print(f"  [{self.id}] {self.name}: could not remove {file_path}: "
                          f"{e.__class__.__name__}: {e}")
