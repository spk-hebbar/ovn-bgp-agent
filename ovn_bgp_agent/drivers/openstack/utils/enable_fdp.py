import os
import socket
import struct
import sys
import asyncore

from enum import IntEnum
from oslo_log import log as logging

from ovn_bgp_agent.drivers.openstack.utils.fpm import fpm_pb2
from ovn_bgp_agent.drivers.openstack.utils.qpb import qpb_pb2

LOG = logging.getLogger(__name__)
# To enable FPM module with protobuf, the following option in
# /etc/frr/daemons needs to be added for zebra
# zebra_options="  -A 127.0.0.1 -s 90000000  -M fpm:protobuf"
FPM_PORT=2620

class Protocol(IntEnum):
    UNKNOWN_PROTO = 0
    LOCAL = 1
    CONNECTED = 2
    KERNEL = 3
    STATIC = 4
    RIP = 5
    RIPNG = 6
    OSPF = 7
    ISIS = 8
    BGP = 9
    OTHER = 10

class FpmServerConnect(asyncore.dispatcher):
    def __init__(self, FPM_PORT):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('localhost', FPM_PORT))
        self.listen(1)

    def run(self):
        try:
            asyncore.loop()
        except asyncore.ExitNow:
            LOG.error("asynccore loop exiting")

    def handle_accept(self):
        pair = self.accept( )
        if pair is not None:
            conn, client_addr = pair
            UpdateRoutes(conn)

class UpdateRoutes(asyncore.dispatcher):
    def update_FRR_route_to_NBDB(self, route):
        zebra_msg = fpm_pb2.Message()
        zebra_msg.ParseFromString(route)
        if zebra_msg.add_route:
            r = zebra_msg.add_route
            if r.address_family == qpb_pb2.AddressFamily.IPV4:
                while len(r.key.prefix.bytes) < 4:
                    r.key.prefix.bytes += b'\0'
                dst = socket.inet_ntoa(r.key.prefix.bytes)
                next_hop = ""
                if r.nexthops[0].if_id:
                    next_hop = str(r.nexthops[0].if_id)
                if r.nexthops[0].address:
                    next_hop = socket.inet_ntoa(struct.pack("!I", r.nexthops[0].address.v4.value))
                if r.protocol == Protocol.BGP:
                    LOG.info("ADD IPV4 %s/%d via %s proto BGP to OVN NB DB" % (dst, r.key.prefix.length, next_hop))
                    os.system("ovn-nbctl lr-route-add rtr %s/%d %s " % (dst, r.key.prefix.length, next_hop))

        if zebra_msg.delete_route:
            r = zebra_msg.delete_route
            if r.address_family == qpb_pb2.AddressFamily.IPV4:
                while len(r.key.prefix.bytes) < 4:
                    r.key.prefix.bytes += b'\0'
                dst = socket.inet_ntoa(r.key.prefix.bytes)
                LOG.INFO("DELETE IPV4 %s/%d " % (dst, r.key.prefix.length))
                os.system("ovn-nbctl lr-route-del rtr %s/%d" % (dst, r.key.prefix.length))
        return

    def handle_read(self):
        data = self.recv(4)
        version,msg_type,length = struct.unpack('!BBH', data)
        payload = self.recv(length-4)
        if msg_type == 1:
            LOG.error("Unexpected Netlink message")
            self.close()
            return
        self.update_FRR_route_to_NBDB(payload)

    def handle_error(self):
        self.close()
        raise asyncore.ExitNow('Quitting!')
