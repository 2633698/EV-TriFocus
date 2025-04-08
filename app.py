from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import logging
from datetime import datetime, timedelta
import numpy as np
import time
import threading
import math
import random
import pickle # Added for MARL Q-table saving/loading checks (optional)
import traceback # Add this import
import argparse

# Import your existing modules
from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler
# ev_integration_scheduler imports are now handled within initialize_system if needed explicitly
# from ev_integration_scheduler import IntegratedChargingSystem # No longer directly needed here

app = Flask(__name__, static_folder='static', template_folder='static/templates')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("charging_system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EVApp")
logger.info("Application starting")

# Global variables
simulation_running = False
simulation_thread = None
system = None # system will now be an instance containing env and scheduler
current_state = {
    "timestamp": datetime.now().isoformat(),
    "progress": 0,
    "metrics": {
        "user_satisfaction": 0,
        "operator_profit": 0,
        "grid_friendliness": 0,
        "total_reward": 0
    }
}
previous_states = {} # Store previous state for MARL reward calculation
simulation_step_delay_ms = 100.0 # Default delay per step (100ms for 1x speed)

def load_config():
    # Default config structure for reference:
    default_config = {
            "environment": {
                "grid_id": "DEFAULT001",
                "charger_count": 20,
                "user_count": 50,
                "simulation_days": 7,
                "time_step_minutes": 15
            },
            "model": {
                "input_dim": 19,
                "hidden_dim": 128,
                "task_hidden_dim": 64,
                "model_path": "models/ev_charging_model.pth" # Ensure this exists if use_trained_model is true
            },
            "scheduler": {
                "use_trained_model": False, # Still potentially relevant for non-MARL advanced scheduling
                "scheduling_algorithm": "rule_based", # Added default
                "optimization_weights": { # Used by rule_based and coordinated_mas
                    "user_satisfaction": 0.4,
                    "operator_profit": 0.3,
                    "grid_friendliness": 0.3
                },
                "marl_config": { # Added MARL specific config
                     "learning_rate": 0.01,
                     "discount_factor": 0.95,
                     "exploration_rate": 0.1,
                     "q_table_path": "models/marl_q_tables.pkl",
                     "action_space_size": 6 # Example: idle + 5 potential users
                }
            },
            "grid": {
                "base_load": [
                    4000, 3500, 3000, 2800, 2700, 3000, 4500, 6000, 7500, 8000, 8200, 8400,
                    8000, 7500, 7000, 6500, 7000, 7500, 8500, 9000, 8000, 7000, 6000, 5000
                ],
                "peak_hours": [7, 8, 9, 10, 18, 19, 20, 21],
                "valley_hours": [0, 1, 2, 3, 4, 5]
            },
            "visualization": {
                "output_dir": "output"
            },
            "strategies": { # Weights for rule_based and coordinated_mas when selecting strategy
                "balanced": {"user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34},
                "grid": {"user_satisfaction": 0.2, "operator_profit": 0.2, "grid_friendliness": 0.6},
                "profit": {"user_satisfaction": 0.2, "operator_profit": 0.6, "grid_friendliness": 0.2},
                "user": {"user_satisfaction": 0.6, "operator_profit": 0.2, "grid_friendliness": 0.2}
            }
        }
    if os.path.exists('config.json'):
        with open('config.json', 'r', encoding='utf-8') as f:
            # Merge loaded config with defaults to ensure all keys exist
            loaded_config = json.load(f)
            # Deep merge might be better, but simple update works for now
            for key, value in default_config.items():
                if key not in loaded_config:
                    loaded_config[key] = value
                elif isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in loaded_config[key]:
                             loaded_config[key][sub_key] = sub_value
                        elif isinstance(sub_value, dict):
                             for sub_sub_key, sub_sub_value in sub_value.items():
                                  if sub_key in loaded_config[key] and isinstance(loaded_config[key][sub_key], dict) and sub_sub_key not in loaded_config[key][sub_key]:
                                       loaded_config[key][sub_key][sub_sub_key] = sub_sub_value


            return loaded_config
    else:
        # Return default config
        logger.warning("config.json not found, using default configuration.")
        return default_config


# Using a simple namespace for the system object
from types import SimpleNamespace

def initialize_system():
    global system, previous_states
    previous_states = {} # Reset previous states on re-initialization

    try:
        logger.info("Loading configuration")
        config = load_config()

        # Create output directory and model directory
        os.makedirs(config.get("visualization", {}).get("output_dir", "output"), exist_ok=True)
        if config.get("scheduler", {}).get("marl_config", {}).get("q_table_path"):
             q_table_dir = os.path.dirname(config["scheduler"]["marl_config"]["q_table_path"])
             if q_table_dir:
                os.makedirs(q_table_dir, exist_ok=True)
        logger.info("Ensured output/model directories exist")

        system_obj = SimpleNamespace() # Use SimpleNamespace to hold env and scheduler
        system_obj.config = config # Store config within the system object

        # Initialize environment
        logger.info("Initializing ChargingEnvironment")
        # 合并environment和grid配置
        env_config = {
            **config["environment"],
            "grid": config.get("grid", {})  # 添加grid配置
        }
        system_obj.env = ChargingEnvironment(env_config)

        # Initialize scheduler (which handles internal algorithm selection)
        logger.info(f"Initializing ChargingScheduler with algorithm: {config['scheduler'].get('scheduling_algorithm', 'rule_based')}")
        try:
            # Pass the full config to the scheduler
            system_obj.scheduler = ChargingScheduler(config)
            logger.info("Successfully initialized ChargingScheduler")

            # Load Q-tables if MARL is selected
            if system_obj.scheduler.algorithm == "marl" and hasattr(system_obj.scheduler, "load_q_tables"):
                logger.info("Attempting to load MARL Q-tables...")
                system_obj.scheduler.load_q_tables()

        except Exception as e:
             logger.error(f"Error initializing ChargingScheduler: {str(e)}")
             logger.error(traceback.format_exc())
             # Fallback: Create a dummy scheduler if initialization fails
             system_obj.scheduler = SimpleNamespace(
                 make_scheduling_decision=lambda state: {},
                 learn=lambda state, action, reward, next_state: None, # Dummy learn
                 load_q_tables=lambda: None, # Dummy load
                 save_q_tables=lambda: None, # Dummy save
                 algorithm="fallback"
             )

        system = system_obj # Assign the created object to the global 'system'
        logger.info("System initialization completed successfully")
        return system

    except Exception as e:
        logger.error(f"Critical error during system initialization: {str(e)}")
        logger.error(traceback.format_exc())
        # Fallback: Create a minimal dummy system to prevent frontend errors
        minimal_system = SimpleNamespace()
        minimal_system.config = load_config() # Load default config even in failure
        minimal_system.env = SimpleNamespace(
            chargers={}, users={}, 
            # Ensure grid_status exists with default keys
            grid_status={"grid_load": 0, "ev_load": 0, "renewable_ratio": 0, "current_price": 0.8, "peak_hours": [], "valley_hours": []},
            current_time = datetime.now(),
            # Ensure dummy state includes the required keys
            get_current_state=lambda: {
                "timestamp": datetime.now().isoformat(), 
                "users": [], "chargers": [], 
                "grid_load": 0, "ev_load": 0, 
                "renewable_ratio": 0, "current_price": 0.8
            },
            step=lambda decisions: (
                {"user_satisfaction": 0, "operator_profit": 0, "grid_friendliness": 0, "total_reward": 0},
                # Ensure next dummy state also includes keys
                {
                    "timestamp": (datetime.now() + timedelta(minutes=15)).isoformat(), 
                    "users": [], "chargers": [], 
                    "grid_load": 0, "ev_load": 0, 
                    "renewable_ratio": 0, "current_price": 0.8
                },
                False
            ),
             reset=lambda: { # Ensure reset state includes keys
                "timestamp": datetime.now().isoformat(), 
                "users": [], "chargers": [], 
                "grid_load": 0, "ev_load": 0, 
                "renewable_ratio": 0, "current_price": 0.8
            },
             _calculate_rewards=lambda: {"user_satisfaction": 0, "operator_profit": 0, "grid_friendliness": 0, "total_reward": 0} # Add dummy reward calc
        )
        minimal_system.scheduler = SimpleNamespace(
            make_scheduling_decision=lambda state: {},
            learn=lambda state, action, reward, next_state: None,
            load_q_tables=lambda: None,
            save_q_tables=lambda: None,
            algorithm="fallback"
        )
        system = minimal_system # Assign minimal system to global
        return minimal_system


def run_simulation(days, strategy="balanced", algorithm="rule_based"): # Added algorithm parameter
    global current_state, simulation_running, system, previous_states, simulation_step_delay_ms
    previous_states = {} # Clear previous states at the start of a new run

    try:
        # Update config with selected strategy and algorithm
        logger.info(f"Starting simulation with days={days}, strategy={strategy}, algorithm={algorithm}")

        config = load_config() # Load current config

        # Set algorithm
        config["scheduler"]["scheduling_algorithm"] = algorithm

        # Set strategy weights (only relevant for rule_based and coordinated_mas)
        if algorithm in ["rule_based", "coordinated_mas"]:
            if strategy in config["strategies"]:
                config["scheduler"]["optimization_weights"] = config["strategies"][strategy]
                logger.info(f"Using strategy weights for '{strategy}': {config['strategies'][strategy]}")
            else:
                logger.warning(f"Unknown strategy: {strategy}, using default weights for {algorithm}")
                # Ensure default weights are set if strategy is invalid
                if "balanced" in config["strategies"]:
                     config["scheduler"]["optimization_weights"] = config["strategies"]["balanced"]
                else: # Fallback if even 'balanced' is missing
                     config["scheduler"]["optimization_weights"] = {"user_satisfaction": 0.33, "operator_profit": 0.33, "grid_friendliness": 0.34}
        else:
            # For MARL, strategy weights are not directly used in the same way
             logger.info(f"Running MARL algorithm. Strategy '{strategy}' weights not directly applied (internal rewards used).")


        # Save updated config for this run (optional, could just pass it)
        # with open('config.json', 'w', encoding='utf-8') as f:
        #     json.dump(config, f, indent=4)

        # Initialize or reinitialize system with the potentially updated config
        logger.info("Initializing system for simulation run")
        # Pass the modified config directly to initialize_system
        # Note: initialize_system updates the global 'system' variable
        initialize_system_with_config(config) # Use a helper to avoid global confusion

        if not system or not system.env or not system.scheduler:
             logger.error("System initialization failed. Aborting simulation.")
             simulation_running = False
             return

        simulation_running = True
        total_steps = days * 24 * 60 // config["environment"]["time_step_minutes"]
        current_step = 0
        metrics_history = []

        # Reset environment
        state = system.env.reset()
        previous_states = {} # Reset previous state cache
        previous_states['initial_state'] = state  # 存储初始状态供后续使用

        logger.info(f"Starting simulation loop for {total_steps} steps.")

        for step in range(total_steps):
            if not simulation_running:
                logger.info("Simulation stopped externally.")
                break

            current_time_step_start = time.time()

            # Store previous state for MARL reward calculation (deep copy if necessary)
            # We need the state *before* make_scheduling_decision is called
            try:
                current_global_state_for_reward = system.env.get_current_state()
                previous_states['global_for_reward'] = current_global_state_for_reward # Store state before decisions
            except Exception as e:
                 logger.error(f"Error getting current state before decisions: {e}")
                 # Continue with potentially empty previous state

            # --- Decision Making ---
            start_decision_time = time.time()
            # Log the keys of the state being passed to the scheduler
            logger.debug(f"State keys passed to scheduler: {list(current_global_state_for_reward.keys()) if isinstance(current_global_state_for_reward, dict) else 'Invalid State Type'}")
            # The scheduler now internally uses the configured algorithm
            decisions = system.scheduler.make_scheduling_decision(current_global_state_for_reward)
            decision_time = time.time() - start_decision_time
            # logger.debug(f"Step {step}: Decisions made ({decision_time:.3f}s): {decisions}")

            # --- Environment Step ---
            start_env_step_time = time.time()
            rewards, next_state, done = system.env.step(decisions)
            env_step_time = time.time() - start_env_step_time
            # logger.debug(f"Step {step}: Env step done ({env_step_time:.3f}s)")

            # --- MARL Learning Step ---
            start_learn_time = time.time()
            if system.scheduler.algorithm == "marl" and hasattr(system.scheduler, "learn"):
                 prev_state_for_learn = previous_states.get('global_for_reward', {}) # State before decision
                 # MARL system needs state, actions taken (derived from decisions/env step?), rewards, next_state
                 # Need to carefully map decisions/results to agent actions and rewards
                 system.scheduler.learn(prev_state_for_learn, decisions, rewards, next_state) # Pass relevant info
            learn_time = time.time() - start_learn_time
            # logger.debug(f"Step {step}: Learn step done ({learn_time:.3f}s)")

            # --- Record Metrics ---
            metrics_history.append({
                "timestamp": next_state.get("timestamp"), # Use .get() for next_state too
                "rewards": rewards, # Global rewards
                "grid_load": system.env.grid_status.get("grid_load", 0), # Use .get()
                "ev_load": system.env.grid_status.get("ev_load", 0), # Use .get()
                "renewable_ratio": system.env.grid_status.get("renewable_ratio", 0), # Use .get()
                # Include MARL specific metrics if available (e.g., agent rewards)
                # "agent_rewards": system.scheduler.get_last_agent_rewards() if system.scheduler.algorithm == "marl" else {}
            })

            # Update overall current_state for UI
            current_progress = ((step + 1) / total_steps) * 100
            current_state = {
                "timestamp": next_state["timestamp"],
                "progress": current_progress,
                "metrics": rewards, # Use latest global rewards
                "chargers": list(system.env.chargers.values()), # Ensure list format
                "users": list(system.env.users.values()), # Ensure list format
                "grid_status": system.env.grid_status.copy() # Send the full grid status object
            }
            # ADD LOGGING HERE
            logger.debug(f"State Sent - Step {step+1}: Keys={list(current_state.keys())}, GridStatus={current_state.get('grid_status')}")

            # --- Simulation Speed Control ---
            step_duration_actual = time.time() - current_time_step_start
            delay_needed = (simulation_step_delay_ms / 1000.0) - step_duration_actual
            if delay_needed > 0:
                time.sleep(delay_needed)

            step_duration_total = time.time() - current_time_step_start
            # logger.info(f"Step {step+1}/{total_steps} completed ({step_duration_total:.3f}s). Progress: {current_progress:.2f}%")

            if done:
                logger.info("Simulation completed (reached end time).")
                break

            # Optional: small delay to prevent CPU hogging, or for visualization speed control
            # time.sleep(0.01) # Removed in favor of dynamic delay

        # --- Simulation End ---
        logger.info(f"Simulation finished. Recorded {len(metrics_history)} steps.")

        # Final state update for UI
        final_state = system.env.get_current_state()
        final_rewards = system.env._calculate_rewards() # Use final env state for rewards
        current_state = {
            "timestamp": final_state["timestamp"],
            "progress": 100.0,
            "metrics": final_rewards,
            "grid_load": system.env.grid_status.get("grid_load", 0), # Use .get() here too
            "chargers": list(system.env.chargers.values()),
            "users": list(system.env.users.values()),
            "metrics_history": metrics_history # Attach full history
        }

        # Save MARL Q-tables if MARL was used
        if system.scheduler.algorithm == "marl" and hasattr(system.scheduler, "save_q_tables"):
            logger.info("Saving MARL Q-tables...")
            system.scheduler.save_q_tables()

        # Save final results
        result_path = os.path.join(config.get("visualization", {}).get("output_dir", "output"),
                                   f"simulation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            # Prepare data for JSON, using .get() for safety
            state_to_save = {
                 "timestamp": current_state.get("timestamp"),
                 "progress": current_state.get("progress", 100.0),
                 "metrics": current_state.get("metrics", {}),
                 "grid_load": current_state.get("grid_load", 0),
                 "chargers": current_state.get("chargers", []),
                 "users": current_state.get("users", []),
                 "metrics_history": current_state.get("metrics_history", [])
            }
            with open(result_path, 'w', encoding='utf-8') as f:
                # Use custom JSON encoder if numpy types cause issues
                json.dump(state_to_save, f, indent=4, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else str(x))
            logger.info(f"Simulation results saved to {result_path}")
        except TypeError as e:
             logger.error(f"JSON serialization error: {e}. Saving without history.")
             # Try saving without history if it's the cause
             state_to_save.pop('metrics_history', None)
             with open(result_path, 'w', encoding='utf-8') as f:
                 json.dump(state_to_save, f, indent=4, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else str(x))
             logger.info(f"Simulation results (without history) saved to {result_path}")
        except Exception as e:
            logger.error(f"Error saving simulation results: {e}")


    except Exception as e:
        logger.error(f"Simulation run failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        simulation_running = False
        logger.info("Simulation thread terminated")

# Helper to initialize system with a specific config, avoids global issues in run_simulation
def initialize_system_with_config(config_to_use):
     global system
     # Temporarily override config load mechanism
     original_load_config = globals()['load_config']
     globals()['load_config'] = lambda: config_to_use
     try:
         system = initialize_system() # This will now use config_to_use
     finally:
         globals()['load_config'] = original_load_config # Restore original loader
     return system


# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/user')
def user_dashboard():
    return render_template('user.html')

@app.route('/operator')
def operator_dashboard():
    return render_template('operator.html')

@app.route('/grid')
def grid_dashboard():
    return render_template('grid.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    # Ensure latest config is loaded, including defaults for missing keys
    config = load_config()
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration with values from the web interface"""
    try:
        # Get the updated config from request
        updated_config = request.get_json()
        
        if not updated_config:
            error_msg = "接收到空的配置数据"
            logger.error(error_msg)
            return jsonify({"success": False, "error": error_msg})
            
        logger.info(f"接收到配置更新请求: {updated_config}")
        
        # Get current config
        config = load_config()
        
        # 记录更新前的配置
        logger.info(f"更新前的配置: 用户数量={config['environment'].get('user_count')}, 站点数量={config['environment'].get('station_count')}, 每站充电桩数量={config['environment'].get('chargers_per_station')}")
        
        # 更新环境配置的各项参数
        if 'environment' in updated_config:
            env_config = updated_config['environment']
            # 确保保留了所有必要的参数
            for key in env_config:
                if key in config['environment'] or key == 'map_bounds':
                    if key == 'map_bounds' and isinstance(env_config[key], dict):
                        # 特殊处理地图边界
                        if 'map_bounds' not in config['environment']:
                            config['environment']['map_bounds'] = {}
                        for bkey, bval in env_config[key].items():
                            config['environment']['map_bounds'][bkey] = bval
                    else:
                        config['environment'][key] = env_config[key]
            
            # 确保关键参数类型正确
            for key in ['user_count', 'station_count', 'chargers_per_station', 'simulation_days', 'time_step_minutes', 'region_count']:
                if key in config['environment']:
                    try:
                        config['environment'][key] = int(config['environment'][key])
                    except (ValueError, TypeError):
                        logger.warning(f"参数{key}转换为整数失败，使用默认值")
                        # 设置默认值
                        if key == 'user_count':
                            config['environment'][key] = 1000
                        elif key == 'station_count':
                            config['environment'][key] = 20
                        elif key == 'chargers_per_station':
                            config['environment'][key] = 20
                        elif key == 'simulation_days':
                            config['environment'][key] = 7
                        elif key == 'time_step_minutes':
                            config['environment'][key] = 15
                        elif key == 'region_count':
                            config['environment'][key] = 5
        
        # 更新其他配置项
        if 'scheduler' in updated_config and isinstance(updated_config['scheduler'], dict):
            if 'scheduler' not in config:
                config['scheduler'] = {}
            
            for key in updated_config['scheduler']:
                if key == 'optimization_weights' and isinstance(updated_config['scheduler'][key], dict):
                    if 'optimization_weights' not in config['scheduler']:
                        config['scheduler']['optimization_weights'] = {}
                    for wkey, wval in updated_config['scheduler'][key].items():
                        config['scheduler']['optimization_weights'][wkey] = wval
                else:
                    config['scheduler'][key] = updated_config['scheduler'][key]
        
        # 更新模型配置
        if 'model' in updated_config and isinstance(updated_config['model'], dict):
            if 'model' not in config:
                config['model'] = {}
            
            for key in updated_config['model']:
                config['model'][key] = updated_config['model'][key]
        
        # 记录更新后的配置
        logger.info(f"更新后的配置: 用户数量={config['environment'].get('user_count')}, 站点数量={config['environment'].get('station_count')}, 每站充电桩数量={config['environment'].get('chargers_per_station')}")
        
        # Save configuration to file
        try:
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            logger.info("配置已保存到config.json")
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            return jsonify({"success": False, "error": f"保存配置文件失败: {str(e)}"})
        
        # Return the updated configuration
        return jsonify({"success": True, "config": config})
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/simulation/start', methods=['POST'])
def start_simulation():
    global simulation_thread, simulation_running

    if simulation_running:
        return jsonify({"status": "error", "message": "Simulation is already running"})

    data = request.json
    days = data.get('days', 7)
    strategy = data.get('strategy', 'balanced')
    # Get algorithm from request, default to 'rule_based'
    algorithm = data.get('algorithm', 'rule_based')
    valid_algorithms = ["rule_based", "coordinated_mas", "marl", "uncoordinated"]
    if algorithm not in valid_algorithms:
         logger.warning(f"Invalid algorithm '{algorithm}' requested. Defaulting to 'rule_based'.")
         algorithm = "rule_based"


    logger.info(f"Received request to start simulation: days={days}, strategy={strategy}, algorithm={algorithm}")

    # Start simulation in a separate thread
    simulation_thread = threading.Thread(
        target=run_simulation,
        args=(days, strategy, algorithm) # Pass algorithm
    )
    simulation_thread.daemon = True
    simulation_thread.start()

    return jsonify({"status": "success", "message": "Simulation started"})

@app.route('/api/simulation/stop', methods=['POST'])
def stop_simulation():
    global simulation_running
    
    if not simulation_running:
        return jsonify({"status": "error", "message": "No simulation is running"})
    
    simulation_running = False
    return jsonify({"status": "success", "message": "Simulation stopped"})

@app.route('/api/simulation/status', methods=['GET'])
def get_simulation_status():
    global current_state, simulation_running

    # Ensure current_state has basic structure even if simulation hasn't run
    state_to_send = {
         "timestamp": datetime.now().isoformat(),
         "progress": 0,
         "metrics": {},
         "grid_load": 0,
         "chargers": [],
         "users": []
    }
    state_to_send.update(current_state) # Overwrite with actual data if available

    # Ensure chargers and users are lists
    if isinstance(state_to_send.get("chargers"), dict):
        state_to_send["chargers"] = list(state_to_send["chargers"].values())
    if isinstance(state_to_send.get("users"), dict):
        state_to_send["users"] = list(state_to_send["users"].values())


    return jsonify({
        "running": simulation_running,
        "state": state_to_send
    })

@app.route('/api/chargers', methods=['GET'])
def get_chargers():
    if system and system.env:
        return jsonify(list(system.env.chargers.values()))
    return jsonify([])

@app.route('/api/users', methods=['GET'])
def get_users():
    if system and system.env:
        return jsonify(list(system.env.users.values()))
    return jsonify([])

@app.route('/api/grid', methods=['GET'])
def get_grid_status():
    if system and system.env:
        return jsonify(system.env.grid_status)
    return jsonify({})

@app.route('/output/<path:filename>')
def output_file(filename):
    return send_from_directory('output', filename)

# 添加一个API端点获取所有模拟结果
@app.route('/api/simulation/results', methods=['GET'])
def get_simulation_results():
    """获取所有已保存的模拟结果文件"""
    try:
        if not os.path.exists('output'):
            return jsonify({"status": "error", "message": "No output directory found"})
        
        result_files = []
        for file in os.listdir('output'):
            if file.startswith('simulation_result_') and file.endswith('.json'):
                file_path = os.path.join('output', file)
                file_stats = os.stat(file_path)
                
                # 从文件中读取基本信息
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        timestamp = data.get('timestamp', 'Unknown')
                        progress = data.get('progress', 0)
                        metrics = data.get('metrics', {})
                except Exception as e:
                    timestamp = 'Error reading file'
                    progress = 0
                    metrics = {}
                
                result_files.append({
                    "filename": file,
                    "created": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                    "size": file_stats.st_size,
                    "timestamp": timestamp,
                    "progress": progress,
                    "metrics": metrics
                })
        
        # 按创建时间逆序排序
        result_files.sort(key=lambda x: x["created"], reverse=True)
        
        return jsonify({
            "status": "success", 
            "results": result_files
        })
    except Exception as e:
        logger.error(f"Error retrieving simulation results: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

# 添加一个API端点加载特定的模拟结果
@app.route('/api/simulation/result/<filename>', methods=['GET'])
def get_simulation_result(filename):
    """获取特定的模拟结果文件"""
    try:
        result_path = os.path.join('output', filename)
        if not os.path.exists(result_path):
            return jsonify({"status": "error", "message": f"找不到结果文件: {filename}"}), 404
        
        with open(result_path, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
        
        # 提取metrics_history中的指标数据，并转换为前端图表所需的格式
        metrics_series = {}
        
        if 'metrics_history' in result_data and isinstance(result_data['metrics_history'], list) and len(result_data['metrics_history']) > 0:
            logger.info(f"提取metrics_history数据，共有 {len(result_data['metrics_history'])} 个时间点")
            
            # 准备时间序列数据结构
            timestamps = []
            user_satisfaction_values = []
            operator_profit_values = []
            grid_friendliness_values = []
            total_reward_values = []
            grid_load_values = []
            ev_load_values = []
            renewable_ratio_values = []
            
            # 从metrics_history提取数据
            for entry in result_data['metrics_history']:
                if 'timestamp' in entry:
                    timestamps.append(entry['timestamp'])
                    
                    # 从rewards中提取指标
                    if 'rewards' in entry and isinstance(entry['rewards'], dict):
                        rewards = entry['rewards']
                        user_satisfaction_values.append(rewards.get('user_satisfaction', 0))
                        operator_profit_values.append(rewards.get('operator_profit', 0))
                        grid_friendliness_values.append(rewards.get('grid_friendliness', 0))
                        total_reward_values.append(rewards.get('total_reward', 0))
                    else:
                        # 如果没有rewards，使用默认值0
                        user_satisfaction_values.append(0)
                        operator_profit_values.append(0)
                        grid_friendliness_values.append(0)
                        total_reward_values.append(0)
                    
                    # 提取电网负载数据
                    grid_load_values.append(entry.get('grid_load', 0))
                    ev_load_values.append(entry.get('ev_load', 0))
                    renewable_ratio_values.append(entry.get('renewable_ratio', 0))
            
            # 构建metrics_series数据
            metrics_series = {
                'timestamps': timestamps,
                'user_satisfaction': user_satisfaction_values,
                'operator_profit': operator_profit_values,
                'grid_friendliness': grid_friendliness_values,
                'total_reward': total_reward_values,
                'grid_load': grid_load_values,
                'ev_load': ev_load_values,
                'renewable_ratio': renewable_ratio_values
            }
            
            logger.info(f"metrics_series数据已准备好，时间点数量: {len(timestamps)}")
        else:
            logger.warning(f"结果文件 {filename} 中未找到有效的metrics_history数据")
            
            # 如果没有metrics_history，使用单一时间点的数据
            if 'timestamp' in result_data and 'metrics' in result_data:
                metrics_series = {
                    'timestamps': [result_data['timestamp']],
                    'user_satisfaction': [result_data['metrics'].get('user_satisfaction', 0)],
                    'operator_profit': [result_data['metrics'].get('operator_profit', 0)],
                    'grid_friendliness': [result_data['metrics'].get('grid_friendliness', 0)],
                    'total_reward': [result_data['metrics'].get('total_reward', 0)],
                    'grid_load': [result_data.get('grid_load', 0)],
                    'ev_load': [0],
                    'renewable_ratio': [0]
                }
        
        # 返回干净的结果版本
        return jsonify({
            "status": "success", 
            "result": result_data,
            "metrics_series": metrics_series
        })
    except Exception as e:
        logger.error(f"获取模拟结果时出错: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": f"获取模拟结果时出错: {str(e)}"}), 500

# Enhanced routes to add to app.py

@app.route('/api/user/recommendations', methods=['POST'])
def get_user_recommendations():
    """Generate personalized charging recommendations for a user"""
    if not system or not system.env:
        return jsonify({"status": "error", "message": "System not initialized"})
    
    data = request.json
    user_id = data.get('user_id')
    user_preferences = data.get('preferences', {})
    
    # Find user
    user = None
    for u in system.env.users.values():
        if u["user_id"] == user_id:
            user = u
            break
    
    if not user:
        return jsonify({"status": "error", "message": "User not found"})
    
    # Override user preferences if provided
    if user_preferences:
        user["time_sensitivity"] = user_preferences.get("time_sensitivity", user["time_sensitivity"])
        user["price_sensitivity"] = user_preferences.get("price_sensitivity", user["price_sensitivity"])
        user["range_anxiety"] = user_preferences.get("range_anxiety", user["range_anxiety"])
    
    # Generate recommendations
    recommendations = []
    current_hour = datetime.fromisoformat(system.env.current_time.isoformat()).hour
    
    for charger_id, charger in system.env.chargers.items():
        # Skip chargers in failure state
        if charger["status"] == "failure":
            continue
        
        # Calculate distance
        distance = math.sqrt(
            (user["current_position"]["lat"] - charger["position"]["lat"])**2 + 
            (user["current_position"]["lng"] - charger["position"]["lng"])**2
        ) * 111  # Convert to km (rough approximation)
        
        # Estimate waiting time
        queue_length = len(charger["queue"])
        base_wait_time = queue_length * 15  # 15 minutes per user in queue
        
        # Add randomness to waiting time based on time of day
        if current_hour in [7, 8, 9, 18, 19, 20]:  # Peak hours
            wait_time = base_wait_time * (1 + random.uniform(0, 0.3))  # Up to 30% longer wait during peak
        else:
            wait_time = base_wait_time * (1 - random.uniform(0, 0.2))  # Up to 20% shorter wait during off-peak
        
        # Calculate price based on time of day and charger type
        base_price = system.env.grid_status["current_price"]
        if current_hour in [7, 8, 9, 10, 18, 19, 20, 21]:  # Peak hours
            price_multiplier = 1.2
        elif current_hour in [0, 1, 2, 3, 4, 5]:  # Valley hours
            price_multiplier = 0.8
        else:
            price_multiplier = 1.0
        
        # Additional multiplier for charger type
        if charger["type"] == "fast":
            price_multiplier *= 1.15  # 15% premium for fast charging
        
        price = base_price * price_multiplier
        
        # Calculate score based on user preferences
        distance_factor = max(0, 1 - (distance / 20))  # 0-20km scale
        wait_factor = max(0, 1 - (wait_time / 60))  # 0-60min scale
        price_factor = max(0, 1 - (price / 1.5))  # 0-1.5 yuan/kWh scale
        
        # Weight factors according to user preferences
        user_score = (
            distance_factor * (1 - user["time_sensitivity"]) +
            wait_factor * user["time_sensitivity"] +
            price_factor * user["price_sensitivity"]
        )
        
        # Scale to 0-100
        score = min(100, max(0, int(user_score * 100)))
        
        # Calculate expected charging time
        if charger["type"] == "fast":
            charging_time = 30 + random.randint(0, 15)  # 30-45 minutes
        else:
            charging_time = 90 + random.randint(0, 30)  # 90-120 minutes
        
        # Calculate estimated cost
        needed_charge = user["battery_capacity"] * (1 - (user["soc"] / 100))
        estimated_cost = round(needed_charge * price, 1)
        
        recommendations.append({
            "charger_id": charger_id,
            "location": charger["location"],
            "type": charger["type"],
            "distance": round(distance, 1),
            "waiting_time": int(wait_time),
            "price": round(price, 2),
            "charging_power": 120 if charger["type"] == "fast" else 60,
            "queue_length": queue_length,
            "score": score,
            "charging_time": charging_time,
            "estimated_cost": estimated_cost,
            "features": []
        })
        
        # Add feature tags
        if charger["type"] == "fast":
            recommendations[-1]["features"].append("快充")
        
        if price_multiplier < 1.0:
            recommendations[-1]["features"].append("低谷电价")
        
        if "科技园" in charger["location"] or "车站" in charger["location"]:
            recommendations[-1]["features"].append("便利位置")
        
        current_renewable_ratio = system.env.grid_status["renewable_ratio"]
        if current_renewable_ratio > 30:
            recommendations[-1]["features"].append("有光伏")
    
    # Sort recommendations by score (descending)
    recommendations.sort(key=lambda x: -x["score"])
    
    return jsonify({
        "status": "success",
        "user": {
            "id": user["user_id"],
            "soc": user["soc"],
            "time_sensitivity": user["time_sensitivity"],
            "price_sensitivity": user["price_sensitivity"],
            "range_anxiety": user["range_anxiety"],
            "user_profile": user["user_profile"]
        },
        "recommendations": recommendations
    })

@app.route('/api/operator/statistics', methods=['GET'])
def get_operator_statistics():
    """Get operator statistics"""
    if not system or not system.env:
        return jsonify({"status": "error", "message": "System not initialized"})
    
    # Generate time-based statistics
    hourly_transactions = [0] * 24
    hourly_revenue = [0] * 24
    hourly_utilization = [0] * 24
    
    # Get current date for daily calculations
    current_date = system.env.current_time.date()
    
    # Process charging history
    for user in system.env.users.values():
        for session in user.get("charging_history", []):
            if session.get("timestamp"):
                timestamp = datetime.fromisoformat(session["timestamp"])
                hour = timestamp.hour
                
                # Count only sessions from the current date
                if timestamp.date() == current_date:
                    hourly_transactions[hour] += 1
                    hourly_revenue[hour] += session.get("cost", 0)
    
    # Calculate utilization from charger status
    total_chargers = len(system.env.chargers)
    if total_chargers > 0 and hasattr(system.env, "history") and system.env.history:
        for hour in range(24):
            hour_steps = [
                step for step in system.env.history
                if datetime.fromisoformat(step["timestamp"]).hour == hour
            ]
            
            if hour_steps:
                occupied_counts = [
                    sum(1 for c in step.get("chargers", []) if c.get("status") == "occupied")
                    for step in hour_steps
                ]
                hourly_utilization[hour] = sum(occupied_counts) / (len(occupied_counts) * total_chargers) * 100
    
    # Calculate overall statistics
    total_transactions = sum(hourly_transactions)
    total_revenue = sum(hourly_revenue)
    avg_revenue_per_transaction = total_revenue / total_transactions if total_transactions > 0 else 0
    
    # Calculate user type distribution
    user_types = {"private": 0, "taxi": 0, "ride_hailing": 0, "logistics": 0}
    for user in system.env.users.values():
        user_type = user.get("user_type", "private")
        if user_type in user_types:
            user_types[user_type] += 1
    
    # Calculate user profile distribution
    user_profiles = {"urgent": 0, "economic": 0, "balanced": 0, "planned": 0}
    for user in system.env.users.values():
        profile = user.get("user_profile", "balanced")
        if profile in user_profiles:
            user_profiles[profile] += 1
    
    # Calculate location-based statistics
    location_stats = {}
    for charger in system.env.chargers.values():
        location = charger.get("location", "Unknown")
        if location not in location_stats:
            location_stats[location] = {
                "charger_count": 0,
                "utilization": 0,
                "revenue": 0,
                "failures": 0
            }
        
        location_stats[location]["charger_count"] += 1
        location_stats[location]["revenue"] += charger.get("daily_revenue", 0)
        
        if charger.get("status") == "failure":
            location_stats[location]["failures"] += 1
    
    # Calculate revenue composition (simplified)
    revenue_composition = {
        "electricity": total_revenue * 0.65,
        "service_fee": total_revenue * 0.15,
        "membership": total_revenue * 0.10,
        "advertising": total_revenue * 0.05,
        "value_added": total_revenue * 0.05
    }
    
    return jsonify({
        "status": "success",
        "overall_stats": {
            "transaction_count": total_transactions,
            "revenue": round(total_revenue, 2),
            "avg_revenue_per_transaction": round(avg_revenue_per_transaction, 2),
            "avg_utilization": round(sum(hourly_utilization) / 24, 2),
            "avg_charge_time": 42  # Simplification - could be calculated from actual data
        },
        "hourly_stats": {
            "transactions": hourly_transactions,
            "revenue": [round(rev, 2) for rev in hourly_revenue],
            "utilization": [round(util, 2) for util in hourly_utilization]
        },
        "user_distribution": {
            "user_types": user_types,
            "user_profiles": user_profiles
        },
        "location_stats": location_stats,
        "revenue_composition": {k: round(v, 2) for k, v in revenue_composition.items()}
    })

@app.route('/api/grid/statistics', methods=['GET'])
def get_grid_statistics():
    """Get grid statistics"""
    if not system or not system.env:
        return jsonify({"status": "error", "message": "System not initialized"})
    
    # Get base grid status
    grid_status = system.env.grid_status
    
    # Calculate hourly statistics
    hourly_stats = {}
    if hasattr(system.env, "history") and system.env.history:
        for hour in range(24):
            hour_steps = [
                step for step in system.env.history
                if datetime.fromisoformat(step["timestamp"]).hour == hour
            ]
            
            if hour_steps:
                # Calculate average grid load, EV load, renewable ratio for this hour
                avg_grid_load = sum(step.get("grid_load", 0) for step in hour_steps) / len(hour_steps)
                avg_ev_load = sum(step.get("ev_load", 0) for step in hour_steps) / len(hour_steps)
                avg_renewable = sum(step.get("renewable_ratio", 0) for step in hour_steps) / len(hour_steps)
                
                hourly_stats[hour] = {
                    "grid_load": avg_grid_load,
                    "ev_load": avg_ev_load,
                    "renewable_ratio": avg_renewable,
                    "ev_to_grid_ratio": avg_ev_load / avg_grid_load if avg_grid_load > 0 else 0
                }
    
    return jsonify({
        "status": "success",
        "current": {
            "grid_load": grid_status.get("grid_load", 0),
            "ev_load": grid_status.get("ev_load", 0),
            "renewable_ratio": grid_status.get("renewable_ratio", 0),
            "current_price": grid_status.get("current_price", 0)
        },
        "hourly_stats": hourly_stats
    })

@app.route('/api/simulation/speed', methods=['POST'])
def set_simulation_speed_endpoint():
    try:
        data = request.json
        if 'multiplier' in data:
            multiplier = float(data['multiplier'])
            
            # For UI display and logic
            global simulation_speed_multiplier
            simulation_speed_multiplier = multiplier
            
            # For actual simulation speed control
            global simulation_step_delay_ms
            if multiplier == 0:  # Max speed
                simulation_step_delay_ms = 1  # Minimal delay
            else:
                simulation_step_delay_ms = int(50 / multiplier)  # Base delay divided by multiplier
                
            logger.info(f"Simulation speed set to {multiplier}x (step delay: {simulation_step_delay_ms}ms)")
            return jsonify({'success': True, 'message': f'Speed set to {multiplier}x'})
        return jsonify({'success': False, 'message': 'Missing multiplier parameter'})
    except Exception as e:
        logger.error(f"Error setting simulation speed: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 添加函数用于调试MARL问题
def debug_marl_state():
    """
    创建一个特殊的测试状态，确保有足够的低SOC用户和可用充电桩，
    用于强制测试MARL系统是否可以工作。
    
    返回一个标准化的状态字典，可以直接传递给MARL系统。
    """
    # 创建一个最小化但有效的状态
    test_time = datetime.now().isoformat()
    
    # 创建10个用户，全部SOC较低，处于traveling状态
    users = []
    for i in range(10):
        users.append({
            "user_id": f"TEST_USER_{i+1}",
            "soc": 20.0 + i*2,  # 从20%到38%的SOC
            "status": "traveling",  # 所有用户都在寻找充电站
            "current_position": {
                "lat": 30.75 + random.uniform(-0.05, 0.05),
                "lng": 114.25 + random.uniform(-0.05, 0.05)
            },
            "price_sensitivity": 0.5,
            "time_sensitivity": 0.5
        })
    
    # 创建5个充电站，全部available
    chargers = []
    for i in range(5):
        chargers.append({
            "charger_id": f"TEST_CHARGER_{i+1}",
            "status": "available",
            "position": {
                "lat": 30.75 + random.uniform(-0.02, 0.02),
                "lng": 114.25 + random.uniform(-0.02, 0.02)
            },
            "type": "fast" if i % 2 == 0 else "slow",
            "queue": []
        })
    
    # 创建电网状态
    grid_status = {
        "grid_load": 50,
        "ev_load": 10,
        "renewable_ratio": 40,
        "current_price": 0.8,
        "peak_hours": [7, 8, 9, 10, 18, 19, 20, 21],
        "valley_hours": [0, 1, 2, 3, 4, 5]
    }
    
    return {
        "timestamp": test_time,
        "users": users,
        "chargers": chargers,
        "grid_status": grid_status
    }

# 添加调试路由，用于直接测试MARL决策
@app.route('/api/debug/marl_test', methods=['GET'])
def test_marl_endpoint():
    """API端点，直接测试MARL系统的决策过程"""
    try:
        # 创建一个简单的MARL测试环境
        debug_state = debug_marl_state()
        
        # 初始化MARL系统进行测试
        from marl_components import MARLSystem
        test_marl = MARLSystem(
            num_chargers=5,
            action_space_size=6, 
            learning_rate=0.01,
            discount_factor=0.95,
            exploration_rate=0.1,
            q_table_path="models/marl_test_q_tables.pkl"
        )
        
        # 获取MARL的动作决策
        agent_actions = test_marl.choose_actions(debug_state)
        logger.info(f"Test MARL actions: {agent_actions}")
        
        # 创建充电调度器系统来转换这些动作
        from ev_charging_scheduler import ChargingScheduler
        test_scheduler = ChargingScheduler({
            "scheduling_algorithm": "marl",
            "grid_id": "TEST",
            "charger_count": 5,
            "user_count": 10,
            "marl_config": {
                "action_space_size": 6,
                "learning_rate": 0.01,
                "discount_factor": 0.95,
                "exploration_rate": 0.1
            }
        })
        
        # 将动作转换为决策
        decisions = test_scheduler._convert_marl_actions_to_decisions(agent_actions, debug_state)
        logger.info(f"Test MARL decisions: {decisions}")
        
        return jsonify({
            'success': True, 
            'marl_actions': agent_actions,
            'decisions': decisions,
            'message': f'MARL test completed with {len(decisions)} decisions'
        })
    except Exception as e:
        logger.error(f"Error testing MARL: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

def get_system_state():
    global system
    if system is None:
        return {
            "timestamp": datetime.now().isoformat(),
            "progress": 0,
            "metrics": {
                "user_satisfaction": 0,
                "operator_profit": 0,
                "grid_friendliness": 0,
                "total_reward": 0
            },
            "charging_stations": []
        }
    
    try:
        # 获取充电站状态
        charging_stations = []
        for station in system.env.charging_stations:
            total_slots = station["total_slots"]
            occupied_slots = len(station["occupied_slots"])
            utilization_rate = (occupied_slots / total_slots) * 100 if total_slots > 0 else 0
            
            station_info = {
                "id": station["id"],
                "location": station["location"],
                "total_slots": total_slots,
                "occupied_slots": occupied_slots,
                "utilization_rate": round(utilization_rate, 2),
                "power_levels": station["power_levels"],
                "power_slots": station["power_slots"]
            }
            charging_stations.append(station_info)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "progress": system.env.current_step / system.env.total_steps,
            "metrics": {
                "user_satisfaction": system.env.metrics["user_satisfaction"],
                "operator_profit": system.env.metrics["operator_profit"],
                "grid_friendliness": system.env.metrics["grid_friendliness"],
                "total_reward": system.env.metrics["total_reward"]
            },
            "charging_stations": charging_stations
        }
    except Exception as e:
        logger.error(f"Error getting system state: {str(e)}")
        return {
            "timestamp": datetime.now().isoformat(),
            "progress": 0,
            "metrics": {
                "user_satisfaction": 0,
                "operator_profit": 0,
                "grid_friendliness": 0,
                "total_reward": 0
            },
            "charging_stations": []
        }

@app.route('/api/system_state')
def api_system_state():
    return jsonify(get_system_state())

def signal_handler(sig, frame):
     global system
     logger.info('Shutdown signal received. Saving Q-tables if MARL is active...')
     if system and hasattr(system, 'scheduler') and system.scheduler.algorithm == "marl" and hasattr(system.scheduler, "save_q_tables"):
          system.scheduler.save_q_tables()
     logger.info("Exiting.")
     exit(0)

# Uncomment below to enable shutdown hook (might need `import signal` at top)
# import signal
# signal.signal(signal.SIGINT, signal_handler)
# signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    import argparse

    # 添加命令行参数
    parser = argparse.ArgumentParser(description='EV充电调度仿真系统')
    parser.add_argument('--cli', action='store_true', help='使用命令行模式运行，而不启动Web服务器')
    parser.add_argument('--days', type=int, default=7, help='模拟天数 (默认: 7)')
    parser.add_argument('--strategy', type=str, default='balanced', 
                        choices=['balanced', 'user', 'grid', 'profit'],
                        help='优化策略: balanced(平衡), user(用户优先), grid(电网优先), profit(利润优先)')
    parser.add_argument('--algorithm', type=str, default='rule_based',
                        choices=['rule_based', 'coordinated_mas', 'marl', 'uncoordinated'],
                        help='调度算法: rule_based(规则), coordinated_mas(协调MAS), marl, uncoordinated(无序充电)')
    parser.add_argument('--output', type=str, help='输出文件路径 (可选)')
    
    args = parser.parse_args()
    
    # Initialize system at startup
    logger.info("Initializing system on startup...")
    system = initialize_system()

    if args.cli:
        # 命令行模式：直接运行模拟，不启动Web服务器
        logger.info(f"Running in CLI mode with days={args.days}, strategy={args.strategy}, algorithm={args.algorithm}")
        run_simulation(args.days, args.strategy, args.algorithm)
        
        if args.output:
            # 如果指定了输出文件路径，则将结果保存到该路径
            config = load_config()
            output_dir = os.path.dirname(args.output)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            try:
                state_to_save = {
                    "timestamp": current_state.get("timestamp"),
                    "progress": current_state.get("progress", 100.0),
                    "metrics": current_state.get("metrics", {}),
                    "grid_load": current_state.get("grid_load", 0),
                    "chargers": current_state.get("chargers", []),
                    "users": current_state.get("users", []),
                    "metrics_history": current_state.get("metrics_history", [])
                }
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(state_to_save, f, indent=4, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else str(x))
                logger.info(f"Simulation results saved to {args.output}")
            except Exception as e:
                logger.error(f"Error saving simulation results to {args.output}: {e}")
        
        print("\n模拟结束。最终结果:")
        print(f"用户满意度: {current_state.get('metrics', {}).get('user_satisfaction', 0):.4f}")
        print(f"运营商利润: {current_state.get('metrics', {}).get('operator_profit', 0):.4f}")
        print(f"电网友好度: {current_state.get('metrics', {}).get('grid_friendliness', 0):.4f}")
        print(f"综合评分: {current_state.get('metrics', {}).get('total_reward', 0):.4f}")
    else:
        # 网页模式：启动Flask服务器
        logger.info("Starting Flask development server...")
        app.run(debug=True, port=5000, use_reloader=False) # use_reloader=False if threading causes issues

# Uncomment below to enable shutdown hook (might need `import signal` at top)
# import signal
# signal.signal(signal.SIGINT, signal_handler)
# signal.signal(signal.SIGTERM, signal_handler)
