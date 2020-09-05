
from .. import ManyGW2ManyMiner
from ..src import messages
import multiprocessing as mp



ManyMiner.run(port=5432, config_paths=['../gw_configs/gateway1.j'])