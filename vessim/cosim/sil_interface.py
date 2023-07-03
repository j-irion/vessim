from threading import Thread
from typing import List, Dict, Any

from vessim.core.storage import SimpleBattery, DefaultStoragePolicy
from vessim.cosim._util import VessimSimulator, VessimModel
from vessim.sil.http_client import HTTPClient, HTTPClientError
from vessim.sil.node import Node
from vessim.sil.api_server import VessimApiServer
from vessim.sil.stoppable_thread import StoppableThread


class SilInterfaceSim(VessimSimulator):
    """Software-in-the-Loop (SiL) interface simulator that executes the model."""

    META = {
        "type": "time-based",
        "models": {
            "SilInterface": {
                "public": True,
                "params": [
                    "nodes",
                    "battery",
                    "policy",
                    "collection_interval",
                    "api_host",
                    "api_port"
                ],
                "any_inputs": True,
                "attrs": []
            },
        },
    }

    def __init__(self) -> None:
        self.step_size = None
        super().__init__(self.META, _SilInterfaceModel)

    def init(self, sid, time_resolution, step_size, eid_prefix=None):
        self.step_size = step_size
        return super().init(sid, time_resolution, eid_prefix=eid_prefix)

    def finalize(self) -> None:
        """Stops the api server and the collector thread when the simulation finishes."""
        super().finalize()
        for model_instance in self.entities.values():
            model_instance.collector_thread.stop() # type: ignore
            model_instance.collector_thread.join() # type: ignore
            model_instance.api_server.terminate() # type: ignore
            model_instance.api_server.join() # type: ignore

    def next_step(self, time):
        return time + self.step_size


class _SilInterfaceModel(VessimModel):
    """Software-in-the-Loop interface to the energy system simulation.

    TODO this class is still very specific to our paper use case and does not
    generalize well to other scenarios.

    Args:
        nodes: List of vessim SiL nodes.
        battery: SimpleBatteryModel used by the system.
        policy: The (dis)charging policy used to control the battery.
        nodes: List of physical or virtual computing nodes.
        collection_interval: Interval in which `/sim/collet-set` in fetched from
            the API server.
        api_host: Server address for the API.
        api_port: Server port for the API.
    """

    def __init__(
        self,
        nodes: List[Node],
        battery: SimpleBattery,
        policy: DefaultStoragePolicy,
        collection_interval: float,
        api_host: str = "127.0.0.1",
        api_port: int = 8000
    ):
        self.nodes = nodes
        self.updated_nodes: List[Node] = []
        self.battery = battery
        self.policy = policy
        self.p_cons = 0
        self.p_gen = 0
        self.p_grid = 0
        self.ci = 0

        # start server process
        self.api_server = VessimApiServer(api_host, api_port)
        self.api_server.start()
        self.api_server.wait_for_startup_complete()

        # init server values and wait for put request confirmation
        self.http_client = HTTPClient(f"http://{api_host}:{api_port}")
        self.http_client.put("/sim/update", {
            "solar": self.p_gen,
            "ci": self.ci,
            "battery_soc": self.battery.soc(),
        })

        self.collector_thread = StoppableThread(self._api_collector, collection_interval)
        self.collector_thread.start()

    def _api_collector(self):
        """Collects data from the API server.

        TODO implement user defined collection method. Current static
        collection method: most recent entry.
        """
        collection = self.http_client.get("/sim/collect-set")

        if collection["battery_min_soc"]:
            newest_key = max(collection["battery_min_soc"].keys())
            self.battery.min_soc = float(collection["battery_min_soc"][newest_key])

        if collection["battery_grid_charge"]:
            newest_key = max(collection["battery_grid_charge"].keys())
            self.policy.grid_power = float(collection["battery_grid_charge"][newest_key])

        if collection["nodes_power_mode"]:
            newest_key = max(collection["nodes_power_mode"].keys())
            nodes_power_mode = {
                int(k): v for k, v in collection['nodes_power_mode'][newest_key].items()
            }
            for node in self.nodes:
                if node.id in nodes_power_mode[node.id]:
                    node.power_mode = nodes_power_mode[node.id]
                    self.updated_nodes.append(node)

    def step(self, time: int, inputs: dict) -> None:
        inputs = _convert_inputs(inputs)
        self.p_cons = inputs["p_cons"]
        self.p_gen = inputs["p_gen"]
        self.ci = inputs["ci"]
        self.p_grid = inputs["p_grid"]

        # update values to the api server
        def update_api_server():
            try:
                self.http_client.put("/sim/update", {
                    "solar": self.p_gen,
                    "ci": self.ci,
                    "battery_soc": self.battery.soc(),
                })
            except HTTPClientError as e:
                print(e)
        # use thread to not slow down simulation
        api_server_update_thread = Thread(target=update_api_server)
        api_server_update_thread.start()

        # update power mode for the node remotely
        for node in self.updated_nodes:
            http_client = HTTPClient(f"{node.address}:{node.port}")

            def update_node_power_model():
                try:
                    http_client.put("/power_mode", {"power_mode": node.power_mode})
                except HTTPClientError as e:
                    print(e)
            # use thread to not slow down simulation
            node_update_thread = Thread(target=update_node_power_model)
            node_update_thread.start()
            self.updated_nodes.clear()


def _convert_inputs(attrs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Removes Mosaik source entity from input dict.

    Examples:
        >>> _convert_inputs({'p': {'ComputingSystem-0.ComputingSystem_0': -50}})
        {'p': -50}
    """
    result = {}
    for key, val_dict in attrs.items():
        result[key] = list(val_dict.values())[0]
    return result