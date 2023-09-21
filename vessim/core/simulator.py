from abc import ABC
from datetime import datetime
from typing import Union, List, Optional

import pandas as pd

Time = Union[int, float, str, datetime]


class TraceSimulator(ABC):
    """Base class for integrating time-series data into simulation.

    Args:
        actual: The actual time-series data to be used. It should follow this structure:
            ------------------------------------------------------------------------
            Timestamp             Zone A  Zone B  Zone C

            2020-01-01 00:00:00   100     800     700
            2020-01-01 01:00:00   110     850     720
            2020-01-01 02:00:00   105     820     710
            2020-01-01 03:00:00   108     840     730
            ------------------------------------------------------------------------
        forecast: Optional time-series data for forecasted trace. If not provided,
            forecasts are generated from actual data.
            ------------------------------------------------------------------------
            Timestamp                                   Zone A  Zone B  Zone C
                                  2020-01-01 01:00:00   115     850     710
            2020-01-01 00:00:00   2020-01-01 02:00:00   120     850     715
                                  2020-01-01 03:00:00   110     870 	720

                                  2020-01-01 02:00:00   110     830     715
            2020-01-01 01:00:00   2020-01-01 03:00:00   105     860     725
                                  2020-01-01 04:00:00   120     870 	740
            ------------------------------------------------------------------------
    """
    def __init__(
        self,
        actual: Union[pd.Series, pd.DataFrame],
        forecast: Optional[pd.DataFrame]
    ):
        self.actual = actual
        self.forecast = forecast

    def zones(self) -> List:
        """Returns a list of all available zones."""
        return list(self.actual.columns)

    def actual_at(self, dt: Time, zone: Optional[str] = None) -> float:
        """Retrieves actual data point of zone at given time.

        If queried timestamp is not available in the `actual` dataframe, the last valid
        datapoint is being returned.

        Raises:
            ValueError: If there is no available data at apecified zone or time.
        """
        if zone is None:
            if len(self.zones()) == 1:
                zone = self.zones()[0]
            else:
                raise ValueError("Zone needs to be specified.")
        try:
            zone_actual = self.actual[zone]
        except KeyError:
            raise ValueError(f"Cannot retrieve actual data at zone '{zone}'.")
        try:
            return zone_actual.loc[self.data.index.asof(dt)]
        except KeyError:
            raise ValueError(f"Cannot retrieve actual data at {dt} in zone {zone}.")

    def forecast_at(self, dt: Time, end: Time, zone: Optional[str] = None) -> pd.Series:
        if zone is None:
            if len(self.zones()) == 1:
                zone = self.zones()[0]
            else:
                raise ValueError("Zone needs to be specified.")
        try:
            if self.forecast is None:
                zone_forecast = self.actual[zone][dt]
            else:
                zone_forecast = self.forecast[zone]
        except KeyError:
            raise ValueError(f"Cannot retrieve forecast at zone '{zone}'.")
        try:
            return zone_forecast.loc[self.data.index.asof(dt)]
        except KeyError:
            raise ValueError(f"Cannot retrieve actual data at {dt} in zone {zone}.")

    def next_update(self, dt: Time) -> datetime:
        """Returns the next time of when the trace will change.

        This method is being called in the time-based simulation model for Mosaik.
        """
        current_index = self.data.index.asof(dt)
        next_iloc = self.data.index.get_loc(current_index) + 1
        return self.data.index[next_iloc]


class CarbonApi(TraceSimulator):
    """Service for querying the carbon intensity at different times and locations.

    Args:
        data: DataFrame with carbon intensity values. Each index represents a
            timestamp and each column a location.
        unit: Unit of the carbon intensity data: gCO2/kWh (`g_per_kWh`) or lb/MWh
            (`lb_per_MWh`). Note that Vessim internally assumes gCO2/kWh, so choosing
            lb/MWh will simply convert this data to gCO2/kWh.
    """
    def __init__(
        self,
        actual: pd.DataFrame,
        forecast: Optional[pd.DataFrame],
        unit: str = "g_per_kWh"
    ):
        super().__init__(actual, forecast)
        if unit == "lb_per_MWh":
            self.actual = self.actual * 0.45359237
            self.forecast = self.forecast * 0.45359237
        elif unit != "g_per_kWh":
            raise ValueError(f"Carbon intensity unit '{unit}' is not supported.")

    def carbon_intensity_at(self, dt: Time, zone: Optional[str] = None) -> float:
        """Returns the carbon intensity at a given time and zone.

        Raises:
            ValueError: If there is no available data at apecified zone or time.
        """
        return self.actual_at(dt, zone)


class Generator(TraceSimulator):

    def power_at(self, dt: Time, zone: Optional[str] = None) -> float:
        """Returns the power generated at a given time.

        If the queried timestamp is not available in the `data` dataframe, the last valid
        datapoint is being returned.

        Raises:
            ValueError: If there is no available data at apecified zone or time.
        """
        return self.actual_at(dt, zone)
