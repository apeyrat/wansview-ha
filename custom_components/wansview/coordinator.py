from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import WansviewClient, WansviewDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class WansviewDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: WansviewClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=20),
        )
        self.client = client
        self.devices: list[WansviewDevice] = []
        self._store: Store[dict[str, dict[str, Any]]] = Store(hass, 1, f"{DOMAIN}_snapshots")
        self.snapshots: dict[str, dict[str, Any]] = {}
        self._failed_ts: dict[str, str | None] = {}
        self._compare_lock = asyncio.Lock()

    async def _async_setup(self) -> None:
        self.snapshots = await self._store.async_load() or {}

    async def _async_compare_snapshot(self, device: WansviewDevice) -> None:
        """Compare a new cloud snapshot with the previous one; never wakes the camera."""
        did, ts = device.device_id, device.snapshot_ts
        known = self.snapshots.get(did, {})
        if not device.snapshot_url or ts in (known.get("ts"), self._failed_ts.get(did)):
            return
        try:
            async with async_get_clientsession(self.hass).get(
                device.snapshot_url, timeout=ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                cur = await resp.read()
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Cannot download snapshot %s of %s: %s", ts, did, err)
            self._failed_ts[did] = ts
            return
        ref = Path(self.hass.config.path(".storage", f"{DOMAIN}_{did}.jpg"))

        def _compare() -> float | None:
            # Imported here so a missing numpy/Pillow only disables this sensor.
            from .compare import changed_share

            return changed_share(ref.read_bytes(), cur) if ref.exists() else None

        try:
            change = await self.hass.async_add_executor_job(_compare)
        except (ImportError, OSError, ValueError) as err:
            _LOGGER.warning("Cannot compare snapshot %s of %s: %s", ts, did, err)
            self._failed_ts[did] = ts
            return
        self.snapshots[did] = {"ts": ts, "prev_ts": known.get("ts"), "change": change}
        await self._store.async_save(self.snapshots)
        await self.hass.async_add_executor_job(ref.write_bytes, cur)
        if change is not None:
            self.hass.bus.async_fire(
                f"{DOMAIN}_snapshot_change",
                {"device_id": did, "change": round(change * 100, 1),
                 "snapshot_ts": ts, "previous_ts": known.get("ts")},
            )

    async def _async_update_data(self) -> dict[str, Any]:
        self.devices = await self.client.async_devices()
        async with self._compare_lock:
            for device in self.devices:
                if device.battery is not None:
                    await self._async_compare_snapshot(device)
        prev = self.data or {}
        data: dict[str, Any] = {}
        for device in self.devices:
            prev_dev = prev.get(device.device_id, {})
            data[device.device_id] = {
                "floodlight": device.floodlight_state,
                "night_mode": device.night_mode,
                "siren": device.siren_state,
                "motion_full_viewport": (
                    device.motion_full_viewport
                    if device.motion_full_viewport is not None
                    else prev_dev.get("motion_full_viewport")
                ),
                "motion_sensitivity": (
                    device.motion_sensitivity
                    if device.motion_sensitivity is not None
                    else prev_dev.get("motion_sensitivity", 1)
                ),
            }
        return data
