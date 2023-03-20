import os
import time
import typing
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
    4 bytes for checksum        - integer
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

        # Use the sum of the packet array to set the checksum
        pkt_array[247:251] = sum(pkt_array).to_bytes(4, 'little')

        # Convert to bytes object and return it
        pkt = bytes(pkt_array)

        return pkt

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
        return calculated == provided

class Nano_I2CBus:
    '''
    Monitor program for the Nvidia Jetson.
    Acts as an interface for the I2C communication buffer.
    Programs that desire to communicate with the Pi controller
    need to request writes through here. The monitor
    program ensures there are no outstanding
    messages from the controller and writes said data
    to the buffer, or performs needed actions if
    commands from the Pi are in the buffer.
    '''

    buf: str = '/sys/bus/i2c/devices/0-0064/slave-eeprom'
    blocksize: int = 256
    timewait: float = 0.2 # Time delay to help with data transmission

    pkt_self_id: str = 'J'           # This system's packet ID
    pkt_targ_id: str = 'P'           # The target packet ID (RPi)

    def __init__(self):
        self.log = open('logfile', 'w')
        self.vision = False
        print('Nano I2C Ready')

    def write_log(self, msg: str):
        date = time.asctime()

        self.log.write(date + ': ' + msg + '\n')

    def write_pkt(self, response, status, sequence):
        '''
        Takes a string, converts it to bytes to send across I2C to the
        specified target.

        msg limited to 256 bytes.

        Returns number bytes sent
        '''
        pkt = I2CPacket.create_pkt(response, len(response), status, 
                                sequence, self.pkt_self_id)
        
        # If pkt is already in bytes, do nothing
        if type(pkt) == bytes:
            pass

        # Otherwise if the data is a string, encode it with UTF-8
        elif type(pkt) == str:
            pkt = pkt.encode(encoding='UTF-8', errors='replace')

        # Otherwise try to convert it to a bytes object
        else:
            try:
                pkt = bytes(pkt)

            # If this fails, return false
            except:
                return False

        with open(self.buf, 'wb') as buf:
            return buf.write(pkt)

    def read_pkt(self, size: int = blocksize):
        '''
        Reads from the eeprom buffer.
        Returns the data as a bytes object.
        '''
        # Open buffer and return first 256 bytes
        with open(self.buf, 'rb') as buf:
            return buf.read(self.blocksize)

    def wait_response(self):
        '''
        Blocks for one second or until the target responds
        Returns resulting packet, if valid packet is received
        Returns false otherwise
        '''
        # Timeout in 1 second
        timeout = time.time() + 3

        # Continuously check the Pi for its response
        while timeout > time.time():

            # Get the packet from the Pi and Parse
            data = self.read_pkt()
            pkt = I2CPacket.parse_pkt(data)

            # Grab sender ID to know if transmission was complete
            sender = pkt[I2CPacket.id_index].decode(errors='ignore')

            # If the sender ID is not ourselves, we received a transmission
            if sender != self.pkt_self_id:

                # Check its integrity (checksum)
                if I2CPacket.verify_pkt(data):
                    return pkt
                else:
                    # If invalid, send an error message so pi resends it
                    print('Requesting new packet (invalid)')
                    self.write_pkt(b'', 'e', 0)

        # If timeout occurs, return false
        self.write_log('Timeout occured. Returning false.')
        return False
    
    def file_send(self, filename: str):
        '''
        Send a file from the jetson to the pi
        '''
        sequence = 0

        # Send File name and wait for a response to start
        if not self.send_and_wait(filename.encode(), 'd', sequence):
            print('Error writing packet')
            self.write_log('Error writing data')
            return False
        
        print('Starting Transmission')

        # Try to open requested file for reading
        try:
            reqfile = open(filename, 'rb')

        # Ignore File Not Found exceptions and move on to ending transmission
        except FileNotFoundError:
            self.write_log('File does not exist')

        # If open was successful, start transferring data
        else:
            with reqfile:
                # Read first chunk of data
                data = reqfile.read(I2CPacket.data_len)
                # While we are still grabbing data from the file
                while data:
                    # Write data to buffer to be sent
                    if not self.send_and_wait(data, 'd', sequence):
                        print('Error writing packet')
                        self.write_log('Error writing data')
                        return False
                
                    sequence += 1

                    # Read next chunk of data
                    data = reqfile.read(I2CPacket.data_len)

        # End transmission
        # Notify Pi transmission is over
        self.write_pkt(b'end', 't', sequence)

        self.write_log('Ending transmission')

        print('Ending transmission')
        
    def send_and_wait(self, data: bytes, status: str, sequence: int):
        '''
        Send a packet, make continuous reads, resend packets if receiver
        sends an error message.

        Return false if an error occured (timeout or error writing)
        Return packet if non-error packet received
        '''

        # Sent packet and wait for a response
        while True:
            # Write packet, return false if it fails
            if not self.write_pkt(data, status, sequence):
                return False

            # Grab result of the wait
            result = self.wait_response()
            
            # If wait returns false, return false
            if not result:
                return False

            # Otherwise if packet was received
            else:
                # Resend packet if an error packet was received
                if result[I2CPacket.stat_index] == b'e':
                    pass

                # Return packet if non-error
                else:
                    return result
