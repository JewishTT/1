"""Measure the two things that silently cap collection volume.

1. Redirect loss. We refuse to follow redirects, which is the correct SSRF posture, but
   sources that answer with a 302 and an empty body are lost entirely. The count matters:
   a redirect is a one-hop address, and there is a way to follow it that keeps the
   reserved-range refusal.
2. Keyless reachability. How many of the 121 keyless sources actually answer, and what
   the status distribution looks like, so the catalogue's real coverage is measured rather
   than assumed.
"""

import asyncio
from collections import Counter

from sources.catalogue import load_catalogue
from sources.executor import HttpSourceExecutor

TARGET = "example.com"


async def main() -> int:
    defs, _ = load_catalogue()
    keyless = [d for d in defs if not d.requires_key and d.enabled and d.kind == "http"]
    print(f"keyless http sources: {len(keyless)}")
    print(f"query: {TARGET!r}")
    print()

    executor = HttpSourceExecutor(timeout=10.0)
    statuses: Counter[int] = Counter()
    redirect_hop: list[tuple[str, str]] = []
    answered = 0
    transport_fail = 0
    multi_page = 0

    try:
        for src in keyless:
            if src.pagination.enabled and src.pagination.page_size:
                multi_page += 1
            try:
                async for cap in executor.capture(src, TARGET):
                    statuses[cap.status] += 1
                    answered += 1
                    if cap.status in (301, 302, 303, 307, 308):
                        redirect_hop.append((src.name, cap.url))
                    break  # one page is enough to measure reachability
            except Exception:
                transport_fail += 1
    finally:
        await executor.aclose()

    print("СТАТУСЫ ПЕРВОЙ СТРАНИЦЫ:")
    for code, n in sorted(statuses.items()):
        tag = ""
        if 200 <= code < 300:
            tag = "  <- данные"
        elif 300 <= code < 400:
            tag = "  <- РЕДИРЕКТ, теряем тело"
        elif code == 400:
            tag = "  <- форма запроса не подошёл под цель"
        elif code == 401 or code == 403:
            tag = "  <- нужен ключ, хотя declares requires_key:false"
        elif code == 404:
            tag = "  <- цель не найдена (валидный ответ)"
        elif code >= 500:
            tag = "  <- ошибка источника"
        print(f"   {code}: {n:>3}{tag}")

    print()
    print(f"источников ответило      : {answered}")
    print(f"транспортных отказов     : {transport_fail}")
    print(f"редиректов (потеря тела) : {len(redirect_hop)}")
    for name, url in redirect_hop[:8]:
        print(f"     {name:<28} {url[:88]}")
    print(f"источников с пагинацией  : {multi_page}")

    real_data = sum(n for c, n in statuses.items() if 200 <= c < 300)
    print()
    print(f"РЕАЛЬНО ДАННЫХ (2xx)     : {real_data} из {len(keyless)} источников")
    if redirect_hop:
        print(
            f"  +{len(redirect_hop)} станут доступны при безопасном следовании редиректам"
            f"  =>  {real_data + len(redirect_hop)} из {len(keyless)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
