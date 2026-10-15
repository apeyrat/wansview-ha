from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import WansviewDevice
from .const import DOMAIN
from .coordinator import WansviewDataUpdateCoordinator
from .entity import WansviewEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WansviewDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WansviewSnapshotImage(hass, coordinator, device)
        for device in coordinator.devices
        if device.snapshot_url
    )


class WansviewSnapshotImage(WansviewEntity, ImageEntity):
    """Last snapshot stored in the cloud; reading it never wakes the camera."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: WansviewDataUpdateCoordinator,
        device: WansviewDevice,
    ) -> None:
        WansviewEntity.__init__(self, coordinator, device)
        ImageEntity.__init__(self, hass)
        self._attr_name = f"{device.name} Snapshot"
        self._attr_unique_id = f"{device.unique_id}_snapshot"
        self._ts: str | None = "unset"
        self._update_from_device()

    def _update_from_device(self) -> None:
        dev = self._dev
        # The cloud URL may be re-signed on each fetch: always keep the latest one.
        self._attr_image_url = dev.snapshot_url
        if dev.snapshot_ts == self._ts:
            return
        self._ts = dev.snapshot_ts
        self._cached_image = None
        try:
            self._attr_image_last_updated = datetime.fromtimestamp(
                int(self._ts) / 1000, tz=UTC
            )
        except (TypeError, ValueError):
            self._attr_image_last_updated = datetime.now(UTC)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_device()
        super()._handle_coordinator_update()
