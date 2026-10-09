"""End-to-end against a running server: connect, play, see checks land.

    <AP venv python> tests/live_check.py ws://localhost:38299 Bo1
"""

import asyncio
import os
import sys

AP = os.environ.get("AP_ROOT", "C:/Users/turtl/Archipelago")
sys.path.insert(0, AP)
os.chdir(AP)
import ModuleUpdate  # noqa: E402

ModuleUpdate.update_ran = True

from CommonClient import server_loop  # noqa: E402
from worlds.apbo.client.context import BoContext  # noqa: E402


async def wait_for(cond, timeout=15.0):
    for _ in range(int(timeout * 10)):
        if cond():
            return True
        await asyncio.sleep(0.1)
    return False


async def main(url: str, name: str) -> int:
    ctx = BoContext(url, None)
    ctx.auth = name
    ctx.server_task = asyncio.create_task(server_loop(ctx))
    ctx.client_loop = asyncio.create_task(ctx.bo_loop())
    ok = await wait_for(lambda: ctx.restore_state == "done" and ctx.session.unlocked_tables)
    print("connected + restored:", ok, "tables", sorted(ctx.session.unlocked_tables))
    missing_before = len(ctx.missing_locations)
    cmd = ctx.command_processor(ctx)
    for _ in range(4):
        table = min(ctx.session.unlocked_tables)
        cmd(f"/play {table}")
        cmd("/autogame")
        await asyncio.sleep(0.5)
    await wait_for(lambda: not ctx.pending_locations)
    await asyncio.sleep(1.5)
    missing_after = len(ctx.missing_locations)
    print(f"won {ctx.session.stats.games_won}/4; missing {missing_before} -> {missing_after}; "
          f"items received {len(ctx.items_received)}")
    ctx.exit_event.set()
    await ctx.shutdown()
    return 0 if missing_after < missing_before else 1


sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
