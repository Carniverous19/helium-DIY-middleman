
"""

This file listens for UDP datagrams on the specified port.
These datagrams should be from lora packet forwarders.  Those that are successfully parsed
will be added to a queue for further processing


"""

import socket
from queue import SimpleQueue, Empty, Full
import logging
import threading
import time

import datetime as dt
if __name__ == "__main__":
    from messages import decode_message, encode_message
else:
    from .messages import decode_message, encode_message

"""
        logging.basicConfig(
            filename=logpath,
            format='%(asctime)s [%(levelname)8s] %(message)s',
            datefmt='%Y/%m/%d %H:%M:%S',
            level=logging.DEBUG if debug else logging.WARNING
        )
        if rx_queue is None or tx_queue is None:
            raise ValueError("rx_queue and tx_queue must be provided")
        self.socket = boundsocket
        self.rx_queue = rx_queue
        self.tx_queue = tx_queue
        self.bind_ip = '0.0.0.0'
        self.debug = debug
"""

def listen(boundsocket=socket, rx_queue=None, tx_queue=None, logger=None):
    """

    :param boundsocket:
    :param rx_queue:
    :type rx_queue: SimpleQueue
    :param tx_queue: send
    :type tx_queue: SimpleQueue
    :param debug: if true print debug messages
    """

    try:

        logging.info(f"RECV - starting listener thread")
        loop_count = 0
        while True:
            data, addr = boundsocket.recvfrom(1024)
            if not data:
                continue
            try:
                msg, ack = decode_message(data, return_ack=True)
            except ValueError as e:
                logger.warning(f"invalid message from ({addr}) '{data}' with exception {e}")
                continue

            # send acknowledgement to original gateway if appropriate for this message type
            if ack:
                boundsocket.sendto(ack, addr)


            if msg['_NAME_'] == 'PUSH_DATA':
                payload = msg['data']

                if 'rxpk' in payload:

                    try:
                        rx_queue.put_nowait(msg)
                        logger.debug(f"RECV({loop_count:4}) - received rxpk message from MAC:{msg['MAC'][-8:]}, queue size: {rx_queue.qsize()}")
                    except Full as e:
                        logger.error(f"RECV({loop_count:4}) - failed to put PUSH_DATA on queue from MAC:{msg['MAC'][-8:]}, queue size: {rx_queue.qsize()}")
                        pass
                elif 'stat' in payload:
                    # drop stat messages for now, not required
                    logger.debug(f"RECV({loop_count:4}) - received stat message from gateway MAC:{msg['MAC'][-8:]}")
                    pass

            elif msg['_NAME_'] == 'PULL_DATA':
                try:
                    tx_queue.put_nowait(
                        ('addr', {msg['MAC']: addr})
                    )
                except Full as e:
                    logger.error(f"RECV({loop_count:4}) - failed to put address for {msg['MAC'][-8:]}")
                    pass
            loop_count += 1
    except Exception as e:
        logger.fatal(f"RECV({loop_count:4}) - listener.py exited, no longer forwarding packets to miner")
        raise e

def transmit(boundsocket, tx_queue, logger):
    """

    :param boundsocket: UDP socket bound to port
    :param tx_queue: queue that will fill with new gateway addresses or transmit payloads, this is only consumer
        producers are listen() and virtual gateways
    :type tx_queue: SimpleQueue
    """
    mac_addresses = dict()
    logging.info(f"TRNS - starting transmitter thread")
    loop_count = 0
    try:
        while True:
            new_item = tx_queue.get()
            if new_item[0] == 'addr':
                # payload should be ("addr", dict(macaddr=(ip, port))
                mac, addr = new_item[1].popitem()
                if mac not in mac_addresses:
                    logger.info(f"TRNS({loop_count:4}) - new gateway with mac:{mac} at {addr}")
                elif mac_addresses[mac] != addr:
                    logger.debug(f"TRNS({loop_count:4}) - new address for mac:{mac}. from {mac_addresses[mac]} to {addr}")
                mac_addresses[mac] = addr
            elif new_item[0] == 'tx':
                # payload should be ("tx", dict(macaddr=payload))
                mac, payload = new_item[1]
                if mac in mac_addresses:
                    # sends payload originating from listening port (so acks go to listener)
                    # sends to IP, port of last received PULL_DATA from this gateway mac address
                    try:
                        raw_tx = encode_message(payload)
                    except Exception as e:
                        logger.error(f"failed to parse PULL_RESP for gw:{mac[-8:]}, payload:{payload}")
                    boundsocket.sendto(raw_tx, mac_addresses[mac])
                    obj = payload['data']['txpk']
                    logger.debug(f"TRNS({loop_count:4}) - sending {obj.get('size')} byte payload from mac:{mac[-8:]} on freq:{obj.get('freq'):.2f}, bw:{obj.get('datr')}")
                else:
                    logger.warning(f"TRNS({loop_count:4}) - tx command for mac:{mac} without known address, dropping")
                    # no known address for this mac
            loop_count += 1
    except Exception as e:
        logger.fatal(f"TRNS({loop_count:4}) - listener.py exited, no longer forwarding packets to miner")
        raise e



def start_server(listening_port, rx_queue, tx_queue):
    """

    :param listening_port: port real gateways should connect to for tx or rx data
    :param rx_queue:
    :param tx_queue:
    :param debug:
    :return:
    """


    logger = logging.getLogger('SRV')

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", listening_port))
        logger.info(f"server listening on port {listening_port}")
        # start transmitter
        transmit_thread = threading.Thread(target=transmit, args=(sock, tx_queue, logger))
        transmit_thread.start()
        time.sleep(0.1)
        # start listener
        listener_thread = threading.Thread(target=listen, args=(sock, rx_queue, tx_queue, logger))
        listener_thread.start()
        while listener_thread.is_alive() and listener_thread.is_alive():
            time.sleep(1)
        logger.fatal(f"atleast one server thread terminated, check logs and restart")

        # not sure this actually exists the thread if there are running children?
        raise RuntimeError("at least one server thread terminated, check logs and restart")



def start_server_thread(listening_port, rx_queue, tx_queue, logpath=None, debug=False):
    thread = threading.Thread(target=start_server, kwargs=dict(listening_port=listening_port, rx_queue=rx_queue, tx_queue=tx_queue))
    thread.start()
    return thread

if __name__ == '__main__':
    rx_queue = SimpleQueue()
    tx_queue = SimpleQueue()
    debug = True
    logformat = '%(asctime)s %(name)-4s:[%(levelname)-8s] %(message)s'
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

    start_server(9000, rx_queue=rx_queue, tx_queue=tx_queue)