"""Мгновенное обновление экранов без опроса раз в N секунд (long-poll).

Ключ 0 — «что-то изменилось в бронях вообще» (обновляет свободное время и админку).
Ключ = ID клиента — личные уведомления клиента. Версии живут в памяти.
"""
import asyncio


class Hub:
    def __init__(self) -> None:
        self._version: dict[int, int] = {}
        self._waiters: dict[int, list[asyncio.Future]] = {}

    def version(self, key: int) -> int:
        return self._version.get(key, 0)

    def publish(self, *keys: int) -> None:
        for key in keys:
            self._version[key] = self.version(key) + 1
            for fut in self._waiters.pop(key, []):
                if not fut.done():
                    fut.set_result(None)

    async def wait(self, key: int, since: int | None, timeout: float = 25.0) -> tuple[int, bool]:
        current = self.version(key)
        if since is None:
            return current, False
        if current != since:
            return current, True
        fut = asyncio.get_running_loop().create_future()
        self._waiters.setdefault(key, []).append(fut)
        try:
            await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            waiters = self._waiters.get(key)
            if waiters and fut in waiters:
                waiters.remove(fut)
        now = self.version(key)
        return now, now != since


hub = Hub()
