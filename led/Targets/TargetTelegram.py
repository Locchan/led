import requests

from led.Interfaces.EventTarget import EventTarget


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
            if files:
                # Endpoint for sending files
                url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"

                for file_path in files:
                    with open(file_path, 'rb') as f:
                        payload = {
                            'chat_id': chat_id,
                            'caption': message,  # The text message appears as the file caption
                            'parse_mode': 'HTML'  # Optional: allows bold/italic in caption
                        }
                        files_payload = {'document': f}
                        requests.post(url, data=payload, files=files_payload, timeout=30)
            else:
                # Original endpoint for plain text
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                requests.post(url, data=payload, timeout=10)
