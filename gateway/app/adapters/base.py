from abc import ABC, abstractmethod

from app.schemas import CommandDispatch, TelemetryFrame


class AbstractDeviceAdapter(ABC):
    """
    Contract every device adapter must implement.
    The gateway loop calls these methods; all device-specific logic stays inside.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialise the physical or simulated connection to the drone."""

    @abstractmethod
    async def read_telemetry(self) -> TelemetryFrame:
        """
        Return one validated TelemetryFrame.
        Blocks until the frame is ready (e.g. after sleeping 1/hz seconds).
        Caller must have set agent_id before the first call.
        """

    @abstractmethod
    async def send_command(self, command: CommandDispatch) -> None:
        """
        Deliver an emergency command to the drone and update internal state.
        Must not raise — log and swallow errors.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up the connection."""
