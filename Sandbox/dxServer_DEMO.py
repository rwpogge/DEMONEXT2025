import os
import sys
import socket
import select

udpAddr = "127.0.0.1"
udpPort = 10501
timeout = 60.0 # housekeeping timeout in seconds

debug = False

# functions

def cmdReply(msgType,cmdWord,msgStr,source,sock,remAddr):
    if source is sys.stdin:
        print(f"{msgType.upper()}: {cmdWord.upper()} {msgStr}")
    elif source is sock:
        replyStr = f"{msgType.upper()}: {cmdWord.upper()} {msgStr}"
        print(f"{remAddr[0]}:{remAddr[1]}>> {replyStr}")
        sock.sendto(replyStr.encode("utf-8"),remAddr)

    return

# main

try:
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind((udpAddr,udpPort))
    sock.setblocking(False)
    print(f"UDP server started on {udpAddr}:{udpPort}")
    print("  type \"quit\" or Ctrl+C to exit.")
except Exception as err:
    print(f"Cannot start UDP server - {err}")
    print("dxServer aborting with errors")
    sys.exit(1)

# Server command loop
#  accept commands from the keyboard or UDP socket host.
#  terminate on "quit" from the client or keyboard, or Ctrl+C at keyboard

try:
    while True:
        readData, _, _ = select.select([sys.stdin,sock],[],[],timeout)

        # handle timeout

        if not readData:
            print("Timeout reached, doing housekeeping...")
            continue

        # we got input on the socket or keyboard, process

        for resource in readData:
            if resource is sys.stdin:
                cmdStr = sys.stdin.readline().strip()
                remAddr = None

            elif resource is sock:
                remData, remAddr = sock.recvfrom(1024)
                cmdStr = remData.strip().decode("utf-8")
                if debug: print(f"Got \"{cmdStr}\" from {remAddr}")
                
        # command tree
        
        if len(cmdStr) > 0:
            cmdBits = cmdStr.split()
            cmdWord = cmdBits[0].lower()
            cmdArgs = cmdBits[1:]
            
            if cmdWord == "quit":
                msgStr = "Shutting down the DEMONEXT server"
                cmdReply("done",cmdWord,msgStr,resource,sock,remAddr)
                break

            elif cmdWord == "startup":
                msgStr = "Doing full DEMONEXT system startup..."
                cmdReply("status",cmdWord,msgStr,resource,sock,remAddr)

            elif cmdWord == "shutdown":
                msgStr = "Doing full DEMONEXT system shutdown..."
                cmdReply("status",cmdWord,msgStr,resource,sock,remAddr)

            elif cmdWord == "status":
                msgStr = "DEMONEXT system status is ..."
                cmdReply("status",cmdWord,msgStr,resource,sock,remAddr)

            else:
                msgStr = f"Unrecognized command \"{cmdStr}\""
                cmdReply("error",cmdWord,msgStr,resource,sock,remAddr)

# Ctrl+C handler

except KeyboardInterrupt:
    print("\nReceived Ctrl+C, server aborted at console")
    print("doing shutdown now...")
    sock.close()
    sys.exit(0)
    
finally:
    sock.close()
    sys.exit(0)

print("Got here by quit...")
sock.close()
print("Done, server session shutdown")
sys.exit(0)
