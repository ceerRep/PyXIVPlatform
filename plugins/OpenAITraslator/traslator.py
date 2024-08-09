import PyXIVPlatform
import LogScanner
import XIVMemory
import PostNamazuWrapper
import CommandHelper

from openai import AsyncOpenAI


class OpenAITraslator:
    def __init__(self):
        self._config = PyXIVPlatform.instance.load_config(__package__)
        self._enabled: bool = self._config["enabled"]
        self._endpoint: str = self._config["endpoint"]
        self._model: str = self._config["model"]
        self._apikey: str = self._config["apikey"]
        self._systemprompt: str = self._config["systemprompt"]
        LogScanner.instance.log_listener(self.on_log_arrival)
        print(self._endpoint)
        self._client = AsyncOpenAI(
            base_url=self._endpoint +
            ("/v1" if self._endpoint[-1] != '/' else 'v1'),
            api_key=self._apikey,
        )

    async def on_log_arrival(self, log: LogScanner.XIVLogLine, process: XIVMemory.XIVProcess):
        if self._enabled and log.new:
            if log.type in [0x3d, 0x39]:
                content = log.fields[0] + ': ' + ' '.join(log.fields[1:])
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": self._systemprompt},
                        {"role": "user", "content": content}
                    ],
                    temperature=0.3
                )
                await PostNamazuWrapper.instance.send_cmd(f"/e [ORIG]: {content}\n[CHN]: {response.choices[0].message.content}")
