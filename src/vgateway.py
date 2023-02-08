import datetime as dt
import time
import random
import logging

if __name__ == "__main__":
    from modify_rxpk import RXMetadataModification
    from messages import decode_message, encode_message, MsgPullData, MsgPushData, MsgPullResp
else:
    from .modify_rxpk import RXMetadataModification
    from .messages import decode_message, encode_message, MsgPullData, MsgPushData, MsgPullResp


class VirtualGateway:
    def __init__(self, mac, server_address, port_up, port_dn, rx_power_adjustment):
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


        # counts number of received and transmitted packets for stats
        self.rxnb = 0
        self.txnb = 0


        # payload modifier
        self.rxmodifier = RXMetadataModification(rx_power_adjustment)

        self.logger = logging.getLogger(f"VGW:{self.mac[-2:]}")


    def get_stat(self):
        """
        return data, address where data is raw bytearray to send from socket and address is the destination (port, ip)
        if no message should be sent returns None, None
        :return:
        """
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
        return self.__get_PUSH_DATA__(payload)

    def get_rxpks(self, msg):
        new_rxpks = []


        # next iterate through each received packet to see if it is a repeat from chached
        for rx in msg['data']['rxpk']:

            # modify metadata as needed
            modified_rx = self.rxmodifier.modify_rxpk(rx, src_mac=msg['MAC'], dest_mac=self.mac)

            # add rx payload to array to be sent to miner
            new_rxpks.append(modified_rx)

        if not new_rxpks:
            return None, None
        payload = dict(rxpk=new_rxpks)

        self.rxnb += len(new_rxpks)
        self.logger.debug(f"sending PUSH_DATA with {len(new_rxpks)} packets from vGW:{self.mac[-8:]} to miner {(self.server_address, self.port_up)}")
        return self.__get_PUSH_DATA__(payload)

    def __get_PUSH_DATA__(self, payload):
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
        return payload_raw, (self.server_address, self.port_up)

    def get_PULL_DATA(self):
        payload = dict(
            _NAME_=MsgPullData.NAME,
            identifier=MsgPullData.IDENT,
            ver=2,
            token=random.randint(0, 2**16-1),
            MAC=self.mac
        )
        payload_raw = encode_message(payload)
        return payload_raw, (self.server_address, self.port_dn)
