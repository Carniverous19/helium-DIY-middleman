
"""

This file listens for UDP datagrams on the specified port.
These datagrams should be from lora packet forwarders.  Those that are successfully parsed
will be added to a queue for further processing


"""

import socket
from queue import SimpleQueue, Empty, Full
import logging
import threading

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

def listener(boundsocket=socket, rx_queue=None, tx_queue=None):
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
            msg, ack = decode_message(data, return_ack=True)

            # send acknowledgement to original gateway if appropriate for this message type
            if ack:
                boundsocket.sendto(ack, addr)


            if msg['_NAME_'] == 'PUSH_DATA':
                payload = msg['data']
                if 'stat' in payload:
                    # drop stat messages for now, not required
                    logging.debug(f"RECV({loop_count:4}) - received stat message from gateway MAC:{msg['MAC']}")
                    pass
                elif 'rxpk' in payload:

                    try:
                        rx_queue.put_nowait(msg)
                        logging.debug(f"RECV({loop_count:4}) - received rxpk message from MAC:{msg['MAC']}, queue size: {rx_queue.qsize()}")
                    except Full as e:
                        logging.error(f"RECV({loop_count:4}) - failed to put PUSH_DATA on queue from MAC:{msg['MAC']}, queue size: {rx_queue.qsize()}")
                        pass

            elif msg['_NAME_'] == 'PULL_DATA':
                logging.debug(f"RECV({loop_count:4}) - received PULL_DATA from gateway MAC: {msg['MAC']}")
                try:
                    tx_queue.put_nowait(
                        ('addr', {msg['MAC']: addr})
                    )
                except Full as e:
                    logging.error(f"RECV({loop_count:4}) - failed to put address for {msg['MAC']}")
                    pass
            loop_count += 1
    except Exception as e:
        logging.fatal(f"RECV({loop_count:4}) - listener.py exited, no longer forwarding packets to miner")
        raise e

def transmit(boundsocket, tx_queue):
    """

    :param boundsocket: UDP socket bound to port
    :param tx_queue: queue that will fill with new gateway addresses or transmit payloads, this is only consumer
        producers are listen() and virtual gateways
    :type tx_queue: SimpleQueue
    """
    mac_addresses = dict()
    logging.info(f"TRANS- starting transmitter thread")
    loop_count = 0
    try:
        while True:
            new_item = tx_queue.get()
            if new_item[0] == 'addr':
                # payload should be ("addr", dict(macaddr=(ip, port))
                mac, addr = new_item[1].popitem()
                if mac not in mac_addresses:
                    logging.info(f"TRANS({loop_count:4})- new gateway with mac:{mac} at {addr}")
                elif mac_addresses[mac] != addr:
                    logging.debug(f"TRANS({loop_count:4})- new address for mac:{mac}. from {mac_addresses[mac]} to {addr}")
                mac_addresses[mac] = addr
            elif new_item[0] == 'tx':
                # payload should be ("tx", dict(macaddr=payload))
                mac, payload = new_item[1].popitem()
                if mac in mac_addresses:
                    # sends payload originating from listening port (so acks go to listener)
                    # sends to IP, port of last received PULL_DATA from this gateway mac address
                    boundsocket.sendto(payload, mac_addresses[mac])
                    obj = payload['data']['txpk']
                    logging.debug(f"TRANS({loop_count:4})- sending {obj.get('size')}byte payload for mac:{mac} on freq:{obj.get('freq'):.2f}, bw{obj.get('datr')}")
                else:
                    logging.warning(f"TRANS({loop_count:4})- tx command for mac:{mac} without known address, dropping")
                    # no known address for this mac
            loop_count += 1
    except Exception as e:
        logging.fatal(f"TRANS({loop_count:4})- listener.py exited, no longer forwarding packets to miner")
        raise e



def start_server(listening_port, rx_queue, tx_queue, logpath=None, debug=False):
    """

    :param listening_port: port real gateways should connect to for tx or rx data
    :param rx_queue:
    :param tx_queue:
    :param debug:
    :return:
    """

    logging.basicConfig(
        filename=logpath,
        format='%(asctime)s [%(levelname)8s] %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG if debug else logging.WARNING
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", listening_port))
    # start transmitter
    transmit_thread = threading.Thread(target=transmit, args=(sock, tx_queue))
    transmit_thread.start()
    # start listener
    listener_thread = threading.Thread(target=listener, args=(sock,rx_queue, tx_queue))
    listener_thread.start()

if __name__ == '__main__':
    rx_queue = SimpleQueue()
    tx_queue = SimpleQueue()
    start_server(9000, rx_queue=rx_queue, tx_queue=tx_queue, debug=True)