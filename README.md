# Optimizing Microgrid Composition for Sustainable Data Centers

## 1. Setup
```sh
poetry install
```
## 2. Exhaustive Simulation
### 2.1 Simulate search space exhaustively
```sh
# for Berkeley
poetry run python renewable_battery_analysis.py --config-name config_battery_analysis_sweep --multirun

# for Houston
poetry run python renewable_battery_analysis.py --config-name config_battery_analysis_sweep_houston --multirun
```
### 2.2 Convert results to combined CSV
```sh
poetry run python convert_results_to_df.py -d ./multirun/<date_of_sim>/<time_of_sim> -l berkley # or houston
```


## 3. Hyperparameter optimization
```sh
# for Berkeley
poetry run python renewable_battery_analysis.py --config-name config_battery_analysis_sweep_optuna.yaml --multirun

# for Houston
poetry run python renewable_battery_analysis.py --config-name config_battery_analysis_sweep_optuna_houston.yaml --multirun
```