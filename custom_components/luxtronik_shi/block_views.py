"""Operating mode select and on/off switch derived from the two blocks ``heating_block`` and ``dhw_block``.

Both entities are views: they read the registers ``heating_block`` (10050) and ``dhw_block`` (10051) that are
polled anyway and write them through the normal write path of the coordinator (``async_write``: own-write
bookkeeping, read-back, ``write_failed`` errors). They poll nothing of their own. The blocks are volatile and
deliberately not in ``RESTORE_KEYS``: after a reset or an expired SHI watchdog both read 0 (nothing blocked).

State of the mode select (heating block, hot water block):

* (0, 0) ``heating_dhw``: heating and hot water.
* (0, 1) ``heating``: heating only (hot water blocked).
* (1, 0) ``dhw_hot_water``: hot water only (heating blocked).
* (1, 1) is shown as ``dhw_hot_water`` as well. That is a limit of three options, not a statement about the
  heat pump: the switch (``block_power``) shows the real "off" for (1, 1).

The switch is on unless both blocks are set. Turning it off sets both blocks. Turning it on releases the hot
water block, and only if both blocks are set; the heating block stays as the mode select left it. In any other
state turning it on does nothing.

Write order, because a sequence of two writes can break between the two. The SHI releases every value it holds
when its watchdog expires, and a released block means "run", so the safe direction of a half-done sequence is
fewer blocks, never more:

* A writes to 0 (release) go before writes to 1 (block). A sequence never creates a block before the other
  block is released, so a half-done change from "heating only" to "hot water only" ends in "heating and hot
  water", never in "both blocked".
* Turning off sets the hot water block first, then the heating block: if the second write fails, heating still
  runs and only hot water is blocked.
* After every write the read-back is checked. A write the SHI accepts but does not take (for example while its
  error 816 "multiple SHI write sources" is active, which refuses writes without an error code) stops the
  sequence with an error and the remaining writes are not made.

Block registers 10050/10051 are read back at once: the firmware's pending map (the deferred commit of about
10 s, see ``const.DEFERRED_KEYS``) covers only 10005-10008. That is inferred from the decompilation of the
pending-map entry (``docs/firmware-3.92.3-shi-analysis.md``), not measured live. If a live measurement ever
shows a lag on the blocks, the read-back check would raise ``block_write_not_taken`` (the safe direction) and
the blocks would need a delayed re-check like ``DEFERRED_KEYS``.

Each register is written even when it already reads the wanted value: the cached value is up to one scan
interval old, and a repeated write of the current value is harmless.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import LuxtronikCoordinator
from .registers import (
    BLOCK_MODE_DHW,
    BLOCK_MODE_HEATING,
    BLOCK_MODE_HEATING_DHW,
    BLOCK_MODES,
    BY_KEY,
    Register,
)

HEATING_BLOCK = BY_KEY["heating_block"]
DHW_BLOCK = BY_KEY["dhw_block"]
# The only values a block register is written with: 0 = released, 1 = blocked.
BLOCK_VALUES = (0, 1)

# mode -> (heating block, hot water block)
MODE_BLOCKS: dict[str, tuple[int, int]] = {
    BLOCK_MODE_HEATING_DHW: (0, 0),
    BLOCK_MODE_HEATING: (0, 1),
    BLOCK_MODE_DHW: (1, 0),
}
assert tuple(MODE_BLOCKS) == BLOCK_MODES

Write = tuple[Register, int]


def blocks(coordinator: LuxtronikCoordinator) -> tuple[int, int] | None:
    """(heating block, hot water block) as read, ``None`` if either is missing or not 0/1."""
    data = coordinator.data or {}
    heating, dhw = data.get(HEATING_BLOCK.key), data.get(DHW_BLOCK.key)
    if heating in BLOCK_VALUES and dhw in BLOCK_VALUES:
        return int(heating), int(dhw)
    return None


def mode_for(state: tuple[int, int] | None) -> str | None:
    """The select option for a block state (see the module docstring for (1, 1))."""
    if state is None:
        return None
    heating, dhw = state
    if heating:
        return BLOCK_MODE_DHW
    return BLOCK_MODE_HEATING if dhw else BLOCK_MODE_HEATING_DHW


def power_for(state: tuple[int, int] | None) -> bool | None:
    """Switch state: on unless both blocks are set."""
    if state is None:
        return None
    return state != (1, 1)


def writes_for_mode(mode: str) -> list[Write]:
    """The writes that set ``mode``: releases first, then blocks (see the module docstring)."""
    heating, dhw = MODE_BLOCKS[mode]
    writes = [(HEATING_BLOCK, heating), (DHW_BLOCK, dhw)]
    return sorted(writes, key=lambda write: write[1])  # stable: heating block first among equals


def writes_for_off() -> list[Write]:
    """Both blocks, hot water first so that a failure in between leaves heating running."""
    return [(DHW_BLOCK, 1), (HEATING_BLOCK, 1)]


def writes_for_on(state: tuple[int, int]) -> list[Write]:
    """Release the hot water block, only if both blocks are set; nothing otherwise."""
    return [(DHW_BLOCK, 0)] if state == (1, 1) else []


async def async_write_sequence(
    coordinator: LuxtronikCoordinator,
    plan: Sequence[Write] | Callable[[], Sequence[Write]],
    *,
    read_first: bool = False,
) -> None:
    """Write the registers one after the other through ``async_write`` and check each read-back.

    One sequence at a time across the select and the switch, so two commands cannot interleave their writes.
    ``plan`` may be a callable: it is evaluated under the lock, after the optional ``read_first`` (a read of
    both block registers from the heat pump), so a decision that depends on the current blocks (turning the
    switch on) is made on what the previous sequence left, not on a state read before the lock.

    Plain ``heating_block``/``dhw_block`` switches are not under this lock. A write to a block between the two
    writes of a sequence can make the read-back of the next write differ; the sequence then raises
    ``block_write_not_taken`` instead of writing on. That is intended: two writers of the same block at the
    same time is a conflict to report, not one to resolve.
    """
    async with coordinator.block_sequence_lock:
        if read_first:
            await coordinator.async_read_now((HEATING_BLOCK, DHW_BLOCK))
        writes = plan() if callable(plan) else plan
        for reg, raw in writes:
            if raw not in BLOCK_VALUES:
                raise ValueError(f"{reg.key}: {raw} is outside {BLOCK_VALUES}")
        for reg, raw in writes:
            try:
                await coordinator.async_write(reg, raw)
            except HomeAssistantError as err:
                if err.translation_key != "write_reverted_to_default":
                    raise
                # The coordinator saw the default read back (the firmware reverted the block); for a sequence the
                # message below says what else was not written.
            actual = (coordinator.data or {}).get(reg.key)
            if actual != raw:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="block_write_not_taken",
                    translation_placeholders={"key": reg.key, "expected": str(raw), "actual": str(actual)},
                )


def require_state(coordinator: LuxtronikCoordinator) -> tuple[int, int]:
    """The current block state, or an error if it is not known."""
    state = blocks(coordinator)
    if state is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="block_state_unknown")
    return state
