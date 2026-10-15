from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import WansviewDevice, WansviewError
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
        WansviewSnapshotButton(coordinator, device)
        for device in coordinator.devices
        if device.battery is not None
    )


class WansviewSnapshotButton(WansviewEntity, ButtonEntity):
    """Wakes the camera for one capture (~15 s awake)."""

    _attr_icon = "mdi:camera"

    def __init__(
        self,
        coordinator: WansviewDataUpdateCoordinator,
        device: WansviewDevice,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_name = f"{device.name} Capture"
        self._attr_unique_id = f"{device.unique_id}_capture"
        self._busy = False

    async def async_press(self) -> None:
        # A capture takes up to ~60 s; extra presses meanwhile would wake the camera again.
        if self._busy:
            return
        self._busy = True
        try:
            await self.coordinator.client.async_snapshot(self._dev)
        except WansviewError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            self._busy = False
        await self.coordinator.async_refresh()
