#!/usr/bin/python3

import binascii, fcntl, os, pty, struct, termios, tty
import selectors, time

tags = {
    0xe5: 'RCE',
    0xe2: 'BPMP',
    0xe3: 'SCE',
    0xe0: 'SPE',
    0xe4: 'TZ',
    0xe1: 'CCPLEX',
}

'''
Represents a TCU stream that is identified by its tag. A pseudo terminal is
created for each stream and a terminal emulator can connect to the pseudo
terminal slave to send and receive data on that stream.
'''
class Stream:
    '''
    Initializes the stream given its name and tag. Opens a pseudo terminal
    and stores the path to the slave so that it can be reported to the user
    and passed to a terminal emulator.
    '''
    def __init__(self, name, tag):
        self.name = name
        self.tag = tag

        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)

    '''
    Returns the file descriptor of the PTY master. This is required in order
    for objects of this class to behave file-like.
    '''
    def fileno(self):
        return self.master

    '''
    Writes a string of characters to the pseudo terminal of this stream.
    '''
    def write(self, data):
        return os.write(self.master, data)

    '''
    Reads a string of characters from the pseudo terminal of this stream.
    '''
    def read(self, count):
        return os.read(self.master, count)

'''
Small helper class to deal with TTYs.
'''
class TTY:
    '''
    Creates a TTY object for the TTY specified by the given path.
    '''
    def __init__(self, path, baudrate = 115200):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    '''
    Returns the file descriptor of the TTY master. This is required in order
    for objects of this class to behave file-like.
    '''
    def fileno(self):
        return self.fd

    '''
    Sets the baud rate of the TTY.
    '''
    def set_baud_rate(self, baud_rate):
        attrs = termios.tcgetattr(self.fd)

        if baud_rate == 115200:
            attr = termios.B115200
        else:
            raise Exception('Unsupported baud rate: %u' % baud_rate)

        attrs[4] = attr
        attrs[5] = attr

        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    '''
    Enables raw mode on the TTY.
    '''
    def set_raw(self):
        tty.setraw(self.fd)

    '''
    Establishes an exclusive (write) lock for the TTY.
    '''
    def lock(self):
        args = struct.pack('hhllhhl', fcntl.F_WRLCK, 0, 0, 0, 0, 0, 0)
        fcntl.fcntl(self.fd, fcntl.F_SETLK, args)

    '''
    Write a string of characters to the TTY.
    '''
    def write(self, data):
        return os.write(self.fd, data)

    '''
    Read a string of characters from the TTY.
    '''
    def read(self, count):
        return os.read(self.fd, count)

'''
Implements a demuxer for the Tegra Combined UART.
'''
class Demux:
    '''
    Creates a demuxer for the Tegra Combined UART found on the given TTY.
    '''
    def __init__(self, path):
        self.tty = TTY(path)
        self.streams = { }
        self.escape = False
        self.output = None
        self.input = None

        self.tty.set_baud_rate(115200)
        self.tty.set_raw()
        self.tty.lock()

        for tag, name in tags.items():
            stream = Stream(name, tag)

            self.streams[tag] = stream

    '''
    Returns a dict object containing the TCU streams.
    '''
    def get_streams(self):
        streams = {}

        for stream in self.streams.values():
            streams[stream.name] = stream.path

        return streams

    '''
    Requests a reset of the TCU streams.
    '''
    def reset(self):
        data = bytes([0xff, 0xfd])
        self.tty.write(data)

    '''
    Processes output events from the TTY.
    '''
    def process_output(self, fileobj, mask):
        if mask & selectors.EVENT_READ:
            data = self.tty.read(4096)

            for byte in data:
                if self.escape:
                    if byte in self.streams:
                        stream = self.streams[byte]

                        if stream != self.output:
                            self.output = stream
                    else:
                        if byte == 0xfd:
                            print('TODO: implement reset')
                        else:
                            print('unhandled command: %02x' % byte)

                    self.escape = False
                    continue

                if byte == 0xff:
                    self.escape = True
                    continue

                if not self.output:
                    print('ERROR: data received but no stream is active: %02x' % byte)
                    continue

                self.output.write(bytes([byte]))

    '''
    Processes input events for data coming from the pseudo terminal slaves.
    '''
    def process_input(self, fileobj, mask):
        if mask & selectors.EVENT_READ:
            if self.input != fileobj:
                data = bytes([0xff, fileobj.tag])
                self.tty.write(data)
                self.input = fileobj

            data = fileobj.read(4096)
            try:
                self.tty.write(data)
            except:
                time.sleep(1)
                self.tty.write(data)

    '''
    Sets up I/O multiplexing for the TTY and all pseudo terminal slaves with
    the given selector for use in an application's event loop.
    '''
    def select(self, selector):
        for stream in self.streams.values():
            selector.register(stream, selectors.EVENT_READ, self.process_input)

        selector.register(self.tty, selectors.EVENT_READ, self.process_output)
