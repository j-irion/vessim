import mosaik_api
from simulator.single_model_simulator import SingleModelSimulator
from simulator.simple_battery_model import SimpleBatteryModel
from simulator.redis_docker import RedisDocker
from fastapi import FastAPI, HTTPException
from typing import Dict, List, Any


META = {
    'type': 'time-based',
    'models': {
        'VirtualEnergySystemModel': {
            'public': True,
            'params': [
                'battery',
                'db_host',
                'api_host'
            ],
            'attrs': [
                'consumption',
                'battery',
                'solar',
                'ci',
                'grid_power'
            ],
        },
    },
}


class VirtualEnergySystem(SingleModelSimulator):
    """Virtual Energy System (VES) simulator that executes the VES model."""

    def __init__(self) -> None:
        super().__init__(META, VirtualEnergySystemModel)

    def finalize(self) -> None:
        """
        Overwrites mosaik_api.Simulator.finalize(). Stops the uvicorn server
        after the simulation has finished.
        """
        super().finalize()
        for model_instance in self.entities.values():
            model_instance.redis_docker.stop()

# TODO in the future we have to differentiate between the energy system and the virtualization layers.

class VirtualEnergySystemModel:
    """
    A virtual energy system model.

    Args:
        battery: SimpleBatteryModel used by the system.
        db_host (optional): The host address for the database, defaults to '127.0.0.1'.
        api_host (optional): The host address for the API, defaults to '127.0.0.1'.

    Attributes:
        step_size: The time step in seconds for the model.
        battery: The battery model used by the system.
        battery_grid_charge: The amount of energy charged to the battery from the grid.
        nodes_power_mode: The power mode of individual nodes.
        consumption: The current total energy consumption of the system.
        solar: The current energy generated by solar panels.
        ci: The current public grid carbon intensity.
        grid_power: The total power drawn from or fed back into the grid.
        redis_docker: The Redis Docker instance used by the system.

    """

    def __init__(self, battery: SimpleBatteryModel, db_host: str='127.0.0.1', api_host: str='127.0.0.1'):
        # ves attributes
        self.battery = battery
        self.battery_grid_charge = 0.0
        self.nodes_power_mode = {}
        self.consumption = 0.0
        self.solar = 0.0
        self.ci = 0.0
        self.grid_power = 0.0

        # db & api
        self.redis_docker = RedisDocker(host=db_host)
        f_api = self.init_fastapi()
        self.redis_docker.run(f_api, host=api_host)

        
    def step(self, consumption: float, solar: float, ci: float) -> None:
        """Step the virtual energy system model.
        
        Executes a single time step of the energy system model, calculating
        energy consumption and generation and determining how much power to
        draw from or feed back into the grid. If there is not enough solar
        power available, the method tries to use the battery. If there is
        excess solar power, the method will charge the battery or feed back
        into the grid.
        """
        # update input
        self.consumption = consumption
        self.solar = solar
        self.ci = ci

        # If delta is positive there is excess power,
        # if negative there is a power deficit.
        delta = self.battery_grid_charge + self.solar - self.consumption

        # battery charge is the value the battery is (dis)charged with
        battery_charge = min(self.battery.max_charge_power, max(delta, -self.battery.max_charge_power))

        delta -= battery_charge
        # (dis)charge the battery
        battery_excess = self.battery.update(power=battery_charge,
                                             duration=self.step_size)

        # battery_excess contains the excess energy after an update:
        #   - positive if the battery is fully charged
        #   - negative if the battery is empty
        #   - else 0
        delta -= battery_excess + self.battery_grid_charge
        # draw or feed back into the grid
        self.grid_power = delta


    def init_fastapi(self) -> FastAPI:
        """Initializes the FastAPI application.

        Returns:
            FastAPI: The initialized FastAPI application.
        """
        app = FastAPI()

        self.init_get_routes(app)
        self.init_put_routes(app)

        return app


    def redis_get(self, entry: str) -> any:
        """Method for getting data from Redis database.

        Args:
            entry: The name of the key to retrieve from Redis.

        Returns:
            any: The value retrieved from Redis.

        Raises:
            ValueError: If the key does not exist in Redis.
        """
        value = self.redis_docker.redis.get(entry)
        if value is None:
            raise ValueError(f'entry {entry} does not exist')
        return value


    def init_get_routes(self, app: FastAPI) -> None:
        """Initializes GET routes for a FastAPI.

        With the given route attributes, the initial values of the attributes
        are stored in Redis key-value store.

        Args:
            app (FastAPI): The FastAPI app to add the GET routes to.
        """
        # store attributes and its initial values in Redis key-value store
        redis_init_content = {
            'solar': self.solar,
            'ci': self.ci,
            'battery.soc': self.battery.soc(),
            # TODO implement forecasts:
            #'ci_forecast': self.ci_forecast,
            #'solar_forecast': self.solar_forecast
        }
        self.redis_docker.redis.mset(redis_init_content)

        @app.get('/solar')
        async def get_solar() -> float:
            return float(self.redis_get('solar'))

        @app.get('/ci')
        async def get_ci() -> float:
            return float(self.redis_get('ci'))

        @app.get('/battery-soc')
        async def get_battery_soc() -> float:
            return float(self.redis_get('battery.soc'))


    def init_put_routes(self, app: FastAPI) -> None:
        """Initialize PUT routes for the FastAPI application.

        Two PUT routes are set up: '/ves/battery' to update the battery
        settings, and '/cs/nodes/{item_id}' to update the power mode of a
        specific node. This method handles data validation and updates the
        corresponding attributes in the application instance and Redis
        datastore.

        Args:
            app (FastAPI): The FastAPI application instance to which the PUT routes are added.
        """

        def validate_keys(data: Dict[str, Any], expected_keys: List[str]):
            missing_keys = set(expected_keys) - set(data.keys())
            if missing_keys:
                raise HTTPException(status_code=422, detail=f"Missing keys: {', '.join(missing_keys)}")

        @app.put('/ves/battery')
        async def put_battery(data: Dict[str, float]):
            validate_keys(data, ['min_soc', 'grid_charge'])
            self.battery.min_soc = data['min_soc']
            self.redis_docker.redis.set('battery.min_soc', data['min_soc'])
            self.battery_grid_charge = data['grid_charge']
            self.redis_docker.redis.set('battery_grid_charge', data['grid_charge'])
            return data

        @app.put('/cs/nodes/{item_id}')
        async def put_nodes(data: Dict[str, str], item_id: int):
            validate_keys(data, ['power_mode'])
            power_modes = ['power-saving', 'normal', 'high performance']
            value = data['power_mode']
            if value not in power_modes:
                raise HTTPException(status_code=400, detail=f'{value} is not a valid power mode. Available power modes: {power_modes}')
            self.nodes_power_mode[item_id] = value
            self.redis_docker.redis.hset('nodes_power_mode', str(item_id), value)
            return data


    def print_redis(self):
        """Debugging function that simply prints all entries of the redis db."""

        r = self.redis_docker.redis
        # Start the SCAN iterator
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor)
            for key in keys:
                # Check the type of the key
                key_type = r.type(key)

                # Retrieve the value according to the key type
                if key_type == b'string':
                    value = r.get(key)
                elif key_type == b'hash':
                    value = r.hgetall(key)
                elif key_type == b'list':
                    value = r.lrange(key, 0, -1)
                elif key_type == b'set':
                    value = r.smembers(key)
                elif key_type == b'zset':
                    value = r.zrange(key, 0, -1, withscores=True)
                else:
                    value = None

                print(f"Key: {key}, Type: {key_type}, Value: {value}")

            if cursor == 0:
                break


def main():
    """Start the mosaik simulation."""
    return mosaik_api.start_simulation(VirtualEnergySystem())