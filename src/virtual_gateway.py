
"""

This code interfaces with a single miner and appears to be a standard lora packet forwarder

"""
import json
import datetime as dt
import socket
import threading
import logging
import time
import copy
import random

from queue import SimpleQueue, Full, Empty

if __name__ == "__main__":
    from modify_rxpk import RXMetadataModification
    from messages import decode_message, encode_message, MsgPullData, MsgPushData, MsgPullResp
else:
    from .modify_rxpk import RXMetadataModification
    from .messages import decode_message, encode_message, MsgPullData, MsgPushData, MsgPullResp


class VirtualGateway:
    def __init__(self, mac, socket, server_address, port_up, port_dn, logger):
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
        self.logger = logger
        self.total_rxpk = 0     # track total received packets forwarded by this vgateway
        self.othergw_rxpk = 0   # track received packets forwarded by this vgway not received by paired real gw
        self.last_rxpk_print_ts = 0    # track every

        # counts number of received and transmitted packets for stats
        self.rxnb = 0
        self.txnb = 0

        # stores unique id of recently received packets to avoid repeats
        self.rx_cache = dict()

        # payload modifier
        self.rxmodifier = RXMetadataModification()

    def send_stat(self):
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
            if time.time() - self.rx_cache[key][0] > 15:
                _, recvd = self.rx_cache.pop(key)
                if not recvd:
                    self.othergw_rxpk += 1

        # next iterate through each received packet to see if it is a repeat from chached
        for rx in rxpks['data'].get('rxpk', []):
            key = (rx['datr'], rx['codr'], str(round(rx['freq'], 2)), rx['data'])

            if key in self.rx_cache:
                self.logger.debug(f"(vgw:{self.mac[-8:]}) got repeated message {key} first seen {time.time() - self.rx_cache[key]:.3f}s ago, dropping")
                self.rx_cache[key][1] |= self.mac == rxpks['MAC']
                continue

            # fisrt index in tuple is time received, 2nd is if received by this gateway
            self.rx_cache[key] = [time.time(), self.mac == rxpks['MAC']]

            # modify metadata as needed
            orig_rssi, orig_snr, orig_ts = rx['rssi'], rx['lsnr'], rx['tmst']
            modified_rx = self.rxmodifier.modify_rxpk(rx, src_mac=rxpks['MAC'], dest_mac=self.mac)

            # add rx payload to array to be sent to miner
            self.logger.debug(f"(vgw:{self.mac[-8:]}) new rxpk signal: ({orig_rssi}/{orig_snr}->{rx['rssi']}/{rx['lsnr']}) info:{key}, tmst:{modified_rx['tmst']}")
            new_rxpks.append(modified_rx)
            self.total_rxpk += 1

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
        top = dict(
            _NAME_=MsgPushData.NAME,
            identifier=MsgPushData.IDENT,
            ver=2,
            token=random.randint(0, 2**16-1),
            MAC=self.mac,
            data=payload
        )
        payload_raw = encode_message(top)
        self.socket.sendto(payload_raw, (self.server_address, self.port_up))
        self.logger.debug(f"(vgw:{self.mac[-8:]}) sending PUSH_DATA {list(payload.keys())} to miner {(self.server_address, self.port_up)}")
        if time.time() - self.last_rxpk_print_ts > 360:
            self.logger.info(f"(vgw:{self.mac[-8:]}) packet summary: {self.othergw_rxpk}/{self.total_rxpk} ({self.othergw_rxpk*100/self.total_rxpk if self.total_rxpk else 0:.0f}%) packets from other gateways")
            self.last_rxpk_print_ts = time.time()

    def send_PULL_DATA(self):
        payload = dict(
            _NAME_=MsgPullData.NAME,
            identifier=MsgPullData.IDENT,
            ver=2,
            token=random.randint(0, 2**16-1),
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

def vgateway_handle_push(rx_queue, vgateways):
    """

    :param rx_queue:
    :type rx_queue: SimpleQueue
    :param vgateways:
    :param logger:
    :return:
    """

    while True:
        # wait until packet received from a gateway
        rxpacket = rx_queue.get()
        # send received packet to all virtual gateways
        for vgw in vgateways:
            # need to copy as each vgateway is allowed to modify metadata before forwarding
            vgw.send_rxpks(copy.deepcopy(rxpacket))

def vgateway_handle_pull(boundsocket, tx_queue, vgateways, keepalive=10, stat_keepalive_mult=6, logger=None):
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
    :param keepalive: interval in seconds to send PULL_DATA to keep udp port open for transmits
    :param stat_keepalive_mult: send stat messages at specified multiple of keepalive
    :return:
    """
    if not isinstance(logger, logging.Logger):
        logger = logging.getLogger('abc')
        logger.setLevel(logging.ERROR)

    # make dictionary to quickly lookup VGW object by ip, port
    gateway_by_addr = dict()
    for vgw in vgateways:
        # gateway_by_addr[(vgw.server_address, vgw.port_up)] = vgw
        gateway_by_addr[(vgw.server_address, vgw.port_dn)] = vgw

    last_pull_data = 0
    pulls_since_stat = 0
    while True:
        # first regularly send keep-alive pull_datas to inform miners of gateway presence
        timeout = keepalive - (time.time() - last_pull_data)
        if timeout < 0.050:
            for vgw in vgateways:
                vgw.send_PULL_DATA()
            last_pull_data = time.time()
            pulls_since_stat += 1
            # send stat messages per interval
            if stat_keepalive_mult is not None and pulls_since_stat >= stat_keepalive_mult:
                logger.info(f"triggering stat messages from {len(vgateways)} virtual gateways")
                for vgw in vgateways:
                    vgw.send_stat()
                pulls_since_stat = 0
            continue
        # second if we dont need to send keep-alives, see if we need to transmit data from miners
        boundsocket.settimeout(timeout)
        try:
            data, addr = boundsocket.recvfrom(1024)
        except (socket.timeout, BlockingIOError) as e:
            # if recv timed out, no new data but time to send PULL_DATA or stat message
            continue

        except ConnectionResetError as e:
            # from https://stackoverflow.com/questions/15228272/what-would-cause-a-connectionreset-on-an-udp-socket
            # indicates a previous send operation resulted in an ICMP Port Unreachable message.
            # I am ok suppressing these errors
            continue


        # check that sender address is known and message is response data
        if addr not in gateway_by_addr: # unrecognized origin, skip
            if addr:
                logger.warning(f"received packet from unknown origin {addr}, dropping")
            continue
        try:
            logger.debug(f"received from addr:{addr}, data:{data}")
            msg, ack = decode_message(data, return_ack=True)
            if ack:
                # send ack back to miner if appropriate for this command
                boundsocket.sendto(ack, addr)
        except ValueError as e:
            continue
        if msg['_NAME_'] == MsgPullResp.NAME: # if not a Pull_Resp message its probably an ack, ignore
            try:
                # enqueue pull request to send out to gateway
                vgw = gateway_by_addr[addr]
                tx_queue.put_nowait(('tx', (vgw.mac, msg)))
            except Full:
                logger.error(f"could not put new tx message on full queue (len:{tx_queue.qsize()})")
                continue
            finally:
                logger.debug(f"received tx command for gateway {vgw.mac[-8:]} from miner at {addr}, queue size:{tx_queue.qsize()}")

        else:
            pass
            # this is an ACK or some other payload from the miner that we can drop silently

def start_virtual_gateways(vgateway_port, tx_queue, rx_queue, config_paths=[], debug=False):
    """

    :param vgateway_port: socket port to bind to for interfacing with miners
    :param tx_queue: queue where transmit commands from miners should be put
    :param rx_queue: queue where payloads received from real gateways should be popped
    :param config_paths: list of file paths to gateway configs matching semtechs config standards
        each should include gateway_ID, server_address, server_port_up, server_port_dn
        Note ignores keepalive_interval and stat_interval this is set globally for all gateways
    :return: never returns
    """

    logger = logging.getLogger('VGW')


    # setup UDP port for interfacing with miners
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", vgateway_port))
        logger.info(f"virtual gateways listening on port {vgateway_port}")
        # configure gateway objects
        vgateways = []
        for path in config_paths:
            with open(path, 'r') as fd:
                config = json.load(fd)
                if 'gateway_conf' in config:
                    config = config['gateway_conf']

                mac = ''
                if 'gateway_ID' not in config or 'server_address' not in config:
                    logger.error(f"invalid config file {path}, missing required parameters")
                    continue
                for i in range(0, len(config.get('gateway_ID')), 2):
                    mac += config.get('gateway_ID')[i:i+2] + ':'
                mac = mac[:-1].upper()
                vgateways.append(
                    VirtualGateway(
                        mac=mac,
                        socket=sock,
                        server_address=config.get('server_address'),
                        port_dn=config.get('serv_port_down'),
                        port_up=config.get('serv_port_up'),
                        logger=logger
                    )
                )

        # handle transmit commands from miners, send to gateways
        # (boundsocket, tx_queue, vgateways, keepalive=10, stat_keepalive_mult=6, logger=None):
        pull_thread = threading.Thread(target=vgateway_handle_pull, kwargs=dict(boundsocket=sock, tx_queue=tx_queue, vgateways=vgateways, logger=logger))
        pull_thread.start()
        logger.info(f"started virtual gateway transmit command thread")
        time.sleep(0.1)
        # handle received packets from gateways, forward to all miners
        push_thread = threading.Thread(target=vgateway_handle_push, kwargs=dict(rx_queue=rx_queue, vgateways=vgateways))
        push_thread.start()
        logger.info(f"started virtual gateway LoRa receive packet thread for {len(vgateways)} virtual gateways")

        while push_thread.is_alive() and pull_thread.is_alive():
            time.sleep(1)
        logger.fatal(f"atleast one vgateway thread terminated, check logs and restart")

    # not sure this actually exists the thread if there are running children?
    raise RuntimeError("at least one vgateway thread terminated, check logs and restart")


def start_virtual_gateways_thread(vgateway_port, tx_queue, rx_queue, config_paths=[], debug=False):
    thread = threading.Thread(target=start_virtual_gateways, kwargs=dict(vgateway_port=vgateway_port, tx_queue=tx_queue, rx_queue=rx_queue, config_paths=config_paths, debug=debug))
    thread.start()
    return thread



def main():

    tx_queue = SimpleQueue()
    rx_queue = SimpleQueue()
    config_paths = []
    start_virtual_gateways(7001, tx_queue=tx_queue, rx_queue=rx_queue, config_paths=config_paths, debug=True)

if __name__ == '__main__':
    main()
