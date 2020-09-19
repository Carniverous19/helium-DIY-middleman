
"""
Parses messages as defined in https://github.com/Lora-net/packet_forwarder/blob/master/PROTOCOL.TXT

"""



import json
import datetime as dt
import random
import struct
import time

class Message:
    IDENT = 0xFF
    NAME = "None"

    def __init__(self, data=b''):

        self.data = data

    def decode(self, data=None):
        if data:
            self.data = data
        if not self.data or len(self.data) < 4 or self.data[3] != self.IDENT:
            raise ValueError(f"invalid message {data}")

        if len(self.data) < 4:
            raise ValueError(f"invalid {self.NAME} message")
        result = dict(
            ver=self.data[0],
            token=struct.unpack_from('H', self.data[1:])[0],
            identifier=self.data[3],
            _NAME_=self.NAME,
            _UNIX_TS_=time.time()
        )
        return result

    def encode(self, message_object):
        self.data = struct.pack("=BHB", message_object.get('ver', 2), message_object.get('token'), message_object.get('identifier'))
        return self.data

    def ack(self):
        return None

class MsgPushData(Message):
    IDENT = 0x00
    NAME = "PUSH_DATA"

    def decode(self, data=None):
        result = super().decode(data)
        if len(self.data) < 14:
            raise ValueError(f"invalid {self.NAME} message, too short {len(self.data)}/14 bytes")

        result['MAC'] = ':'.join([f"{x:02X}" for x in self.data[4:12]])
        result['data'] = json.loads(self.data[12:].decode())
        return result

    def encode(self, message_object):
        super().encode(message_object)
        # add MAC address
        self.data += struct.pack('=BBBBBBBB', *[int(x, 16) for x in message_object['MAC'].split(':')])
        # add json payload
        self.data += json.dumps(message_object['data']).encode()
        return self.data

    def ack(self):
        ack = self.data[:3] + bytes([0x01])
        return ack

class MsgPushAck(Message):
    IDENT = 0x01
    NAME = "PUSH_ACK"

class MsgPullData(Message):
    IDENT = 0x02
    NAME = "PULL_DATA"

    def decode(self, data=None):

        result = super().decode(data)
        if len(self.data) < 12:
            raise ValueError(f"invalid {self.NAME} message, too short {len(self.data)}/12 bytes")

        result['MAC'] = ':'.join([f"{x:02X}" for x in self.data[4:12]])

        return result

    def encode(self, message_object):
        super().encode(message_object)
        # add MAC address
        self.data += struct.pack('=BBBBBBBB', *[int(x, 16) for x in message_object['MAC'].split(':')])
        return self.data

    def ack(self):
        ack = self.data[:3] + bytes([0x04])
        return ack

class MsgPullAck(Message):
    IDENT = 0x04
    NAME = "PULL_ACK"


class MsgPullResp(Message):
    IDENT = 0x03
    NAME = "PULL_RESP"

    def decode(self, data=None):

        result = super().decode(data)
        if len(self.data) < 14:
            raise ValueError(f"invalid {self.NAME} message, too short {len(self.data)}/14 bytes")

        result['data'] = json.loads(self.data[4:].decode())
        return result

    def encode(self, message_object):
        super().encode(message_object)
        # add json payload
        self.data += json.dumps(message_object['data']).encode()
        return self.data


class MsgTxAck(Message):
    IDENT = 0x05
    NAME = "TX_ACK"
    def decode(self, data=None):

        result = super().decode(data)
        if len(self.data) < 12:
            raise ValueError(f"invalid {self.NAME} message, too short {len(self.data)}/12 bytes")


        result['MAC'] = ':'.join([f"{x:02X}" for x in self.data[4:12]])
        if len(self.data) > 14:
            result['data'] = json.loads(self.data[12:].decode())
        return result

    def encode(self, message_object):
        super().encode(message_object)
        # add MAC address
        self.data += struct.pack('=BBBBBBBB', *[int(x, 16) for x in message_object['MAC'].split(':')])
        # add json payload
        self.data += json.dumps(message_object['data']).encode()
        return self.data

msg_types = {
    MsgPushData.IDENT: MsgPushData,
    MsgPushAck.IDENT: MsgPushAck,
    MsgPullData.IDENT: MsgPullData,
    MsgPullAck.IDENT: MsgPullAck,
    MsgPullResp.IDENT: MsgPullResp,
    MsgTxAck.IDENT: MsgTxAck
}
msg_types_name = {
    MsgPushData.NAME: MsgPushData,
    MsgPushAck.NAME: MsgPushAck,
    MsgPullData.NAME: MsgPullData,
    MsgPullAck.NAME: MsgPullAck,
    MsgPullResp.NAME: MsgPullResp,
    MsgTxAck.NAME: MsgTxAck
}

def decode_message(rawmsg, return_ack=False):
    if len(rawmsg) < 4 or rawmsg[3] not in msg_types:
        raise ValueError(f"invalid message: {rawmsg}, too short {len(rawmsg)}/4 bytes")

    msg_obj = msg_types[rawmsg[3]](rawmsg)
    msg_body = msg_obj.decode()
    ack = msg_obj.ack()
    if return_ack:
        return msg_body, ack
    return msg_body

def encode_message(message_object):
    if message_object.get('_NAME_') not in msg_types_name:
        raise ValueError("invalid message object")

    msg_obj = msg_types_name[message_object.get('_NAME_')]()
    rawmsg = msg_obj.encode(message_object)
    return rawmsg

def print_message(rawmsg):

    msg_body = decode_message(rawmsg)
    print(msg_body)

def PULL_RESP2PUSH_DATA(pull_resp, src_mac):
    push = dict(
        _NAME_=MsgPushData.NAME,
        identifier=MsgPushData.IDENT,
        ver=2,
        token=random.randint(0, 2**16-1),  # TODO: Make random token
        MAC=src_mac,
        txMAC=src_mac,      # this is used to signal generated from tx originatng at this mac
        payload=None
    )
    txpk = pull_resp['data']['txpk']
    chan = int(round((txpk['freq'] - 903.9) / .2, 0)) + 8
    payload = dict(
        data=txpk['data'],
        size=txpk['size'],
        codr=txpk['codr'],
        datr=txpk['datr'],
        modu=txpk['modu'],
        rfch=txpk['rfch'],
        freq=txpk['freq'],
        tmst=0x00000000,        # tmst will be set appropriate for receiver
        rssi=-113,              # set rssi to some reasonable default
        lsnr=-5.5,              # set lsnr to some reasonable default
        stat=1,                 # CRC is ok
        chan=chan               # channel
    )
    push['data'] = dict(rxpk=[payload])
    return push




def trials():
    payload = dict(
        _NAME_=MsgPullData.NAME,
        identifier=MsgPullData.IDENT,
        ver=2,
        token=0xABCD,  # TODO: Make random token
        MAC='AA:55:5A:00:00:00:00:00'
    )
    print(f"encoding body: {payload}")
    payload_raw = encode_message(payload)
    print(f" to raw: {payload_raw}")
    payload = decode_message(payload_raw)
    print(f"back to body: {payload}")

if __name__ == "__main__":
    trials()
