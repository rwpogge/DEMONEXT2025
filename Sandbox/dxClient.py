#
# launch as ipython -i dxClient.py
#
# This demo is a non-listening client
#

import sys
import socket

timeout = 30.0
dxServer = ("127.0.0.1",10501)

def sendToDX(msg):

    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)

    try:
        s.settimeout(timeout)
        s.sendto(msg.encode('utf-8'),dxServer)
        # wait up to timeout for reply
        reply,server = s.recvfrom(4096)
        print(f"DX> {reply.decode('utf-8')}")

    except socket.timeout:
        print(f"*** ERROR: request timed out")

    except Exception as err:
        print(f"*** Unexpected socket error: {err}")

    s.close()

