
"""

This code interfaces with a single miner and appears to be a standard lora packet forwarder

"""
import json
import datetime as dt
import socket
import threading
import time
from queue import SimpleQueue, Full, Empty
if __name__ == "__main__":
    from modify_rxpk import RXMetadataModification
    from messages import decode_message, encode_message, MsgPullData, MsgPushData, MsgPullResp
else:
    from .modify_rxpk import RXMetadataModification
    from .messages import decode_message, encode_message, MsgPullData, MsgPushData, MsgPullResp

class VirtualGateway:
    def __init__(self, mac, socket, server_address, port_up, port_dn):
        """

        :param mac:
        :param socket:
        :param server_address:
        :param port_up:
        :param port_dn:
        """
        # port
        self.mac = mac
        self.port_up = port_up
        self.port_dn = port_dn
        self.server_address = server_address
        self.socket = socket


        # counts number of received and transmitted packets for stats
        self.rxnb = 0
        self.txnb = 0

        # stores unique id of recently received packets to avoid repeats
        self.rx_cache = dict()

        # ticker offset between real gateway with same MAC and utc timestamp
        self.tmst_offset = 0

        # payload modifier
        self.rxmodifier = RXMetadataModification()

    def __send_stat__(self):
        payload = dict(
            stat=dict(
                time=dt.datetime.utcnow().isoformat()[:19] + " GMT",
                rxnb=self.rxnb,
                rxok=self.rxnb,
                rxfw=self.rxnb,
                txnb=self.txnb,
                dwnb=self.txnb,
                ackr=100.0
            )
        )
        self.__send_PUSH_DATA__(payload)

    def send_rxpks(self, rxpks):
        new_rxpks = []

        # first clear rx cache for anything older than 15 seconds
        for key in list(self.rx_cache.keys()):
            if time.time() - self.rx_cache[key] > 15:
                self.rx_cache.pop(key)

        # next iterate through each received packet to see if it is a repeat from chached
        for rx in rxpks:
            key = (rx['datr'], rx['codr'], str(round(rx['freq'], 2)), rx['data'])
            if key in self.rx_cache:
                continue
            self.rx_cache[key] = time.time()
            # modify metadata as needed
            new_rxpks.append(self.rxmodifier.modify_rxpk(rx))

        if not new_rxpks:
            return
        payload = dict(
            rxpk=new_rxpks
        )

        self.__send_PUSH_DATA__(payload)
        self.rxnb += len(new_rxpks)

    def __send_PUSH_DATA__(self, payload):
        """
        Sends PUSH_DATA message to miner with payload contents
        :param payload: raw payload
        :return:
        """
        payload = dict(
            _NAME_=MsgPushData.NAME,
            identifier=MsgPushData.IDENT,
            ver=2,
            token=0,        # TODO: Make random token
            MAC=self.mac,
            data=payload
        )
        payload_raw = encode_message(payload)
        self.socket.sendto(payload_raw, (self.server_address, self.port_up))

    def send_PULL_DATA(self):
        payload = dict(
            _NAME_=MsgPullData.NAME,
            identifier=MsgPullData.IDENT,
            ver=2,
            token=0,        # TODO: Make random token
            MAC=self.mac
        )
        payload_raw = encode_message(payload)
        self.socket.sendto(payload_raw, (self.server_address, self.port_up))

    def run(self):
        pass



"""
    "gateway_conf": {
        "gateway_ID": "AA555A0000000000",
        /* change with default server address/ports, or overwrite in local_conf.json */
        "server_address": "localhost",
        "serv_port_up": 1680,
        "serv_port_down": 1680,
        /* adjust the following parameters for your network */
        "keepalive_interval": 10,
        "stat_interval": 30,
        "push_timeout_ms": 100,
        /* forward only valid packets */
        "forward_crc_valid": true,
        "forward_crc_error": false,
        "forward_crc_disabled": false,
        "gps_tty_path": "/dev/ttyS0"
    }
"""

def miner_handle_push(rx_queue, vgateways):
    """

    :param rx_queue:
    :type rx_queue: SimpleQueue
    :param vgateways:
    :return:
    """

    # make dictionary to quickly lookup VGW object by ip, port
    gateway_by_addr = dict()
    for vgw in vgateways:
        # gateway_by_addr[(vgw.server_address, vgw.port_up)] = vgw
        gateway_by_addr[(vgw.server_address, vgw.port_dn)] = vgw

    while True:
        # wait until packet received from a gateway
        rxpacket = rx_queue.get()
        # send received packet to all virtual gateways
        for vgw in vgateways:
            vgw.send_rxpks(rxpacket)

def miner_handle_pull(boundsocket, tx_queue, vgateways, keepalive=10):
    """
    This function should run in a thread and will never return.
    It performs two functions:
        1) it regularly sends PULL_DATA to miners (params in vgateways) at keepalive interval
        2) it listens for PULL_RESP data which are transmit commands from miners.  These are compared
            against vgateway server addresses to map to appropraite gateway MAC addresses.  These are
            then pushed onto the tx_queue to be pulled by "server.py"
    :param boundsocket: socket to bound to
    :type boundsocket: socket.socket
    :param tx_queue:
    :type tx_queue: SimpleQueue
    :param vgateways: list of virtual gateway object
    :return:
    """

    # make dictionary to quickly lookup VGW object by ip, port
    gateway_by_addr = dict()
    for vgw in vgateways:
        # gateway_by_addr[(vgw.server_address, vgw.port_up)] = vgw
        gateway_by_addr[(vgw.server_address, vgw.port_dn)] = vgw

    last_pull_data = 0
    while True:
        # first regularly send keep-alive pull_datas to inform miners of gateway presence
        timeout = keepalive - (time.time() - last_pull_data)
        if timeout < 0:
            for vgw in vgateways:
                vgw.send_PULL_DATA()
            last_pull_data = time.time()
            continue
        # second if we dont need to send keep-alives, see if we need to transmit data from miners
        boundsocket.settimeout(max(0, keepalive - (time.time() - last_pull_data)))
        try:
            data, addr = boundsocket.recvfrom(1024)
        except socket.timeout as e:
            data = None
            addr = None

        # check that sender address is known and message is response data

        if addr not in gateway_by_addr: # unrecognized origin, skip
            continue
        try:
            msg = decode_message(data)
        except ValueError as e:
            continue
        if msg['_NAME_'] == MsgPullResp.NAME: # if not a Pull_Resp message its probably an ack, ignore
            try:
                # enqueue pull request to send out to gateway
                vgw = gateway_by_addr[addr]
                tx_queue.put_nowait(('tx', (vgw.mac, msg)))
            except Full:
                continue


def start_miners(vgateway_port, tx_queue, rx_queue, config_paths=[]):
    """

    :param vgateway_port:
    :param tx_queue: queue where transmit commands from miners should be put
    :param rx_queue: queue where payloads received from real gateways should be popped
    :param config_paths: list of file paths to gateway configs maching semtechs config standards
        each should include gateway_ID, server_address, server_port_up, server_port_dn
    :return:
    """


    # setup UDP port for interfacing with miners
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", vgateway_port))

    # configure gateway objects
    vgateways = dict()
    for path in config_paths:
        with open(path, 'r') as fd:
            config = json.load(fd)
            if 'gateway_conf' in config:
                config = config['gateway_conf']

            mac = ''
            for i in range(0, len(config.get('gateway_ID')), 2):
                mac += config.get('gateway_ID')[i:i+2] + ':'
            mac = mac[:-1].upper()
            vgateways[mac] = VirtualGateway(
                mac=mac,
                socket=sock,
                server_address=config.get('server_address'),
                port_dn=config.get('serv_port_down'),
                port_up=config.get('serv_port_up')
            )

    # handle transmit commands from miners, send to gateways
    pull_thread = threading.Thread(target=miner_handle_pull, args=(sock, tx_queue, vgateways))
    pull_thread.start()

    # handle received packets from gateways, forward to all miners
    pull_thread = threading.Thread(target=miner_handle_push, args=(rx_queue, vgateways))
    pull_thread.start()

    # start miner transmitter


def main():

    tx_queue = SimpleQueue()
    rx_queue = SimpleQueue()
    config_paths = []
    start_miners(5000, tx_queue=tx_queue, rx_queue=rx_queue, config_paths=config_paths)

if __name__ == '__main__':
    main()