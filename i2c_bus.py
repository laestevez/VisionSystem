'''
The included library can only sent/receive transmissions up to 256 bytes.
The Jetson's I2C address is hardcoded to 0x64 currently
The Pi provides the I2C bus as a device: "/dev/i2c-1"
'''

import pylibi2c
import time
import struct

class I2CPacket:
    '''
    Contains functions that aim to abstract away all the functionality
    related to packets, mainly building it and verifying packet integrity

    Packet structure:
    Size of data                - Python type
    245 byte for data           - bytes
    1 byte for data length      - integer
    1 byte for status messages  - bytes
    4 bytes for parity          - integer
    4 bytes for sequence number - integer
    1 byte for sender ID        - bytes
    '''

    struct_format: str = '=245sBcIIc'
    data_len: int = 245
    data_index: int = 0
    dlen_index: int = 1
    stat_index: int = 2
    par_index: int = 3
    seq_index: int = 4
    id_index: int = 5

    def create_pkt(data: bytes, size: int, status: str,
                   sequence: int, ID: str):
        '''
        Builds a packet containing the specified data. Adds in checksum.

        Returns bytes object for writing.
        '''
        # Check lengths of input. Return false if packing cannot be done
        if size > I2CPacket.data_len:
            return False

        # Create packet with zero checksum for calculation
        pkt_array = bytearray(struct.pack(I2CPacket.struct_format,
                                            data, size, status[:1].encode(),
                                            0, sequence, ID[:1].encode()))

        # Find checksum and stick individual bytes into place
        pkt_array[247:251] = sum(pkt_array).to_bytes(4, 'little')

        # Convert back into bytes object for returning
        return bytes(pkt_array)

    def parse_pkt(pkt: bytes):
        '''
        Unpacks packet, returns resulting tuple
        '''
        return struct.unpack(I2CPacket.struct_format, pkt)

    def verify_pkt(pkt: bytes):
        '''
        Given a packet, calculates checksum, checks with provided checksum of
        packet.

        Returns True if they match, False if they do not.
        '''
        # Convert to byte array
        pkt_array = bytearray(pkt)

        # Extract checksum from packet
        provided = int.from_bytes(pkt_array[247:251], 'little', signed=False)

        # Substitute checksum with all zeros
        pkt_array[247:251] = bytearray(4)

        # Calculate checksum
        calculated = sum(pkt_array)

        # Return True if matching, False otherwise
        if calculated == provided:
            return True
        else:
            return False

class I2CBus:
    '''
    I2C bus object for the Raspberry Pi to communicate with the Jetson.
    '''

    blocksize: int = 256    # Max bytes capable of sending
    timewait: float = 0.2

    pkt_self_id: str = 'P'
    pkt_targ_id: str = 'J'

    def __init__(self, target = 0x64, dev = '/dev/i2c-1'):
        '''
        Initializes the bus using the imported library.

        Default device address for Jetson is 0x64
        Default device for I2C on Pi is i2c-1
        '''
        self.target = target # I2C address of the target (Jetson)
        self.dev = dev       # I2C bus being used on Pi
        self.bus = pylibi2c.I2CDevice(self.dev, self.target)

    def write_msg(self, data):
        '''
        Takes a string, converts it to bytes to send across I2C to the
        specified target.

        msg limited to 256 bytes.

        Returns number bytes sent
        '''
        # If data is already in bytes, do nothing
        if type(data) == bytes:
            pass

        # Otherwise if the data is a string, encode it with UTF-8
        elif type(data) == str:
            data = data.encode(encoding='UTF-8', errors='replace')

        # Otherwise try to convert it to a bytes object
        else:
            try:
                data = bytes(data)

            # If this fails, return false
            except:
                return False

        return self.bus.write(0x0, data)

    def read_msg(self, size: int = blocksize):
        '''
        Reads the message stored on the Jetson's I2C buffer.

        size limited to 256 bytes.
        '''
        # If size is too big, throw an exception
        if size > self.blocksize:
            raise ValueError

        data = self.bus.read(0x0, size)

        # Read requested size, return bytes object
        return data

    def write_pkt(self, data: bytes, status: str, sequence: int):
        '''
        Builds a packet around the requested data, sends it over I2C to the
        Jetson.
        '''
        pkt = I2CPacket.create_pkt(data, len(data), status, sequence, self.pkt_self_id)

        # Return status of write
        return self.write_msg(pkt)

    def read_pkt(self):
        '''
        Requests a read from the Jetson, unpacks its data if valid,
        and returns the data in the form of a tuple
        '''
        # Timeout in 3 second
        timeout = time.time() + 3

        # Continuously check the Jetson for its response
        while timeout > time.time():
            # Get the packet from the Jetson
            data = self.read_msg()

            # Check its integrity (checksum)
            if not I2CPacket.verify_pkt(data):
                time.sleep(self.timewait)
                continue

            # Parse packet if it is valid and return
            return I2CPacket.parse_pkt(data)

        # If timeout occurs, return false
        return False

    def wait_response(self):
        '''
        Blocks until the target responds

        Returns resulting packet, if valid packet is received
        Returns false otherwise
        '''
        # Timeout in 3 seconds
        timeout = time.time() + 3

        # Continuously check the Jetson for its response
        while timeout > time.time():
            # Get the packet from the Jetson
            data = self.read_msg()

            if type(data) == int:
                return False

            # Parse packet if it is valid
            pkt = I2CPacket.parse_pkt(data)

            # Grab sender ID
            sender = pkt[I2CPacket.id_index].decode(errors='ignore')

            # If the sender doesn't match the target, try again
            if sender != self.pkt_self_id:
                # Check its integrity (checksum)
                if I2CPacket.verify_pkt(data):
                    return pkt

            time.sleep(self.timewait)

        # If timeout occurs, return false
        return False

    def send_and_wait(self, data: bytes, status: str, sequence: int):
        '''
        Send a packet, make continuous reads, resend packets if receiver
        sends an error message.

        Return false if an error occured (timeout or error writing)
        Return packet if non-error packet received
        '''
        i = 0

        # Create packet
        pkt = I2CPacket.create_pkt(data, len(data), status, sequence,
                                   self.pkt_self_id)
        
        # Sent packet and wait for a response
        # Catch external IO errors 5 times before relenting
        while i < 5:
            # Write packet, return false if it fails
            if self.write_msg(pkt) < 0:
                i += 1
                continue

            # Grab result of the wait
            result = self.wait_response()

            # If wait returns false, return false
            if not result:
                i += 1
                continue

            # Otherwise if packet was received
            else:
                # Resend packet if an error packet was received
                if result[I2CPacket.stat_index] == b'e':
                    pass

                # Return packet if non-error
                else:
                    #print('writing data')
                    return result

        raise OSError('Could not establish communication with device')

    def read_file(self):
        '''
        Reads the contents of a file from the Jetson. Works in tandem with the
            monitor on the Jetson's side of the comm channel, as we can only
            receive the file 256 bytes at a time.
        '''
        sequence = 0
        
        # Send command and wait for response with filename
        cmd = 'img'
        pkt = self.send_and_wait(cmd.encode(), 'c', sequence)
        
        # Return false on packet error
        if not pkt:
            return False
        
        # filename
        file = pkt[I2CPacket.data_index].decode().strip('\0')
            
        print('Transmission starting')

        # Open file for writing
        with open(file, 'wb') as new_file:

            # While the Jetson does not terminate the transmission
            while pkt[I2CPacket.stat_index] != b't':
                # Send 'ready' and wait for next packet
                pkt = self.send_and_wait(b'', 'r', sequence)

                # Return false on packet error
                if not pkt:
                    return False
                
                # Grab relevant data
                data = pkt[I2CPacket.data_index]
                data_len = pkt[I2CPacket.dlen_index]

                # Write data to new file
                new_file.write(data[:data_len])

                # Increment packet number
                sequence += 1

        return True  

# Used for testing sending commands and recieving data with the jetson nano
def main():
    bus = I2CBus()

    # test writing a command to get cordinates
    bus.write_pkt(b'cord', 'c', 0)

    # wait for response
    while True:
        pkt = bus.wait_response()
        
        if not pkt:
            continue

        if(pkt[I2CPacket.id_index].decode() != bus.pkt_targ_id) or (pkt[I2CPacket.stat_index] != b'd'):
            continue

        # print received data
        data = pkt[I2CPacket.data_index].decode().strip('\0')
        if data:
            print(data)
            break;

    # test recieving an image file
    data = bus.read_file()
    print(data)


if __name__ == '__main__':
    main()
