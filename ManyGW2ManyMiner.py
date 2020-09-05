
"""




"""
import argparse
from queue import SimpleQueue
import time
import os
import logging
from src.server import start_server_thread
from src.virtual_gateway import start_virtual_gateways_thread





def run( port, config_paths, debug=False):

    logformat = '%(asctime)s.%(msecs)03d %(name)-4s:[%(levelname)-8s] %(message)s'
    logging.basicConfig(
        format=logformat,
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG if debug else logging.INFO,
        filename='middleman.log',
        filemode='a'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    formatter = logging.Formatter(logformat, datefmt='%Y/%m/%d %H:%M:%S')
    # tell the handler to use this format
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    rx_queue = SimpleQueue()
    tx_queue = SimpleQueue()


    # initialize listener (mock miner)
    servt = start_server_thread(
        listening_port=port, rx_queue=rx_queue, tx_queue=tx_queue, logpath=None, debug=debug
    )
    print("server started")
    gatewayt = start_virtual_gateways_thread(
        vgateway_port=9002, tx_queue=tx_queue, rx_queue=rx_queue, config_paths=config_paths, debug=debug
    )
    print("gateways started")


    while servt.is_alive() and gatewayt.is_alive():
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser("forward data from multiple concentrators to multiple miners with coercing of metadata")
    parser.add_argument('-p', '--port', help='port to listen for gateway on', default=1680, type=int)
    parser.add_argument('-c', '--configs', help='path where to locate gateway configs', default='gw_configs/', type=str)
    parser.add_argument('-d', '--debug', action='store_true', help="print verbose debug messages")

    args = parser.parse_args()
    config_paths = []
    for f in os.listdir(args.configs):
        if os.path.isfile(os.path.join(args.configs, f)) and f[-4:].lower() == 'json':
            config_paths.append(os.path.join(args.configs, f))
    print(config_paths)
    run(args.port, config_paths, debug=True)

if __name__ == '__main__':
    main()