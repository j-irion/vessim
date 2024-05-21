from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import count
from typing import Optional
from datetime import datetime
import pandas as pd


class PowerMeter(ABC):
    _ids = count(0)

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def measure(self, now: datetime) -> float:
        """Abstract method to measure and return the current node power demand."""

    def finalize(self) -> None:
        """Perform necessary finalization tasks of a node."""


class MockPowerMeter(PowerMeter):
    def __init__(self, p: float, name: Optional[str] = None):
        if name is None:
            name = f"MockPowerMeter-{next(self._ids)}"
        super().__init__(name)
        if p < 0:
            raise ValueError("p must not be less than 0")
        self._p = p

    def set_power(self, value):
        if value < 0:
            raise ValueError("p must not be less than 0")
        self._p = value

    def measure(self, now: datetime) -> float:
        return self._p


class FilePowerMeter(PowerMeter):
    def __init__(self, file_path: str, unit: Optional[str] = "W", date_format: Optional[str] = None, name: Optional[str] = None):
        if name is None:
            name = f"FilePowerMeter-{next(self._ids)}"
        super().__init__(name)
        self.data = self._load_data(file_path, date_format)
        self.unit = unit

    @staticmethod
    def _load_data(file_path: str, date_format: Optional[str]) -> pd.DataFrame:
        """Load data from a CSV file.

        Args:
            file_path: Path to the CSV file.
            date_format: The format of the date in the CSV file.

        Returns:
            The loaded data as a pandas DataFrame.

        Raises:
            ValueError: If the time index is not monotonic increasing or decreasing, or not unique.
        """
        data = pd.read_csv(file_path, names=['time', 'power'], skiprows=1)
        if date_format:
            data['time'] = pd.to_datetime(data['time'], format=date_format)
        else:
            data['time'] = pd.to_datetime(data['time'])
        data.set_index('time', inplace=True)
        data.sort_index(inplace=True)
        if not data.index.is_monotonic_increasing or data.index.is_monotonic_decreasing:
            raise ValueError("The time index must be monotonic increasing or decreasing.")
        if not data.index.is_unique:
            raise ValueError("The time index must be unique.")
        return data

    @staticmethod
    def _convert_power_to_watts(power: float, unit: str) -> float:
        """Convert the power to watts.

        Args:
            power: The power to be converted.
            unit: The unit of the power.

        Returns:
            The power in watts.
        """
        if unit == "W":
            return power
        elif unit == "kW":
            return power * 1e3
        elif unit == "MW":
            return power * 1e6
        else:
            raise ValueError(f"Unknown unit: {unit}")

    def measure(self, now: datetime) -> float:
        """Measure the power at the given time.

        Args:
            now: The current time.

        Returns:
            The power at the given time.

        Raises:
            ValueError: If no data is available before all available data points.
        """
        last_valid_time = self.data.index.asof(now)
        if pd.isna(last_valid_time):
            raise ValueError(f"No data available before or at {now}")
        return self._convert_power_to_watts(float(self.data.at[last_valid_time, 'power']), self.unit)
