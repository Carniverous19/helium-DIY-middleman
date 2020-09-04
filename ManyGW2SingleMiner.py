
"""




"""
import argparse
import json
from queue import SimpleQueue

from src.server import Listener





def run(configpath='middleman_config.json', debug=False):
    with open(configpath, 'r') as fd:
        config = json.load(fd)

    rx_queue = SimpleQueue()
    tx_queue = SimpleQueue()

    # initialize listener (mock miner)
    listener_obj = Listener(
        port=config.get('listen_port'),
        rx_queue=rx_queue,
        tx_queue=tx_queue,
        localonly=config.get('localonly')
    )



def main():
    parser = argparse.ArgumentParser("forward data from multiple concentrators to single miner with coercing metadata")
    parser.add_argument('-c', '--config', help='path to config file (create with InitializeConfig.py)', default='middleman_config.json', type=str)
    parser.add_argument('-d', '--debug', action='store_true', help="print verbose debug messages")

    args = parser.parse_args()
    run(configpath=args.config, debug=args.debug)

if __name__ == '__main__':
    main()