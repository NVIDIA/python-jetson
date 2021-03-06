#!/usr/bin/python3

import enum, string, sys

from pyftdi.ftdi import Ftdi
from pyftdi.i2c import I2cController
from pyftdi.usbtools import UsbTools, UsbToolsError

class cbus_func(enum.IntEnum):
    CBUS_TXDEN = 0
    CBUS_PWREN = 1
    CBUS_RXLED = 2
    CBUS_TXLED = 3
    CBUS_TXRXLED = 4
    CBUS_SLEEP = 5
    CBUS_CLK48 = 6
    CBUS_CLK24 = 7
    CBUS_CLK12 = 8
    CBUS_CLK6 = 9
    CBUS_IOMODE = 10
    CBUS_BB_WR = 11
    CBUS_BB_RD = 12
    CBUS_BB = 13

'''
Determines whether or not a byte can be printed. Note that this excludes
whitespace that doesn't expand to a single character, such as tab, newline
and carriage-return.
'''
def is_printable(byte):
    if chr(byte) in string.printable:
        if byte >= 32:
            return True

    return False

'''
Prints a hexdump of the given array of bytes to a given file-like object. By
default, an ASCII representation of the hexdump will be printed next to the
hexadecimal values. This can be switched off by passing False for the
use_ascii keyword argument.
'''
def hexdump(data, use_ascii = True, file = sys.stdout):
    if use_ascii:
        dump = ' | '

    offset = 0

    for byte in data:
        print(' %02x' % byte, end = '', file = file)

        if use_ascii:
            if is_printable(byte):
                dump += chr(byte)
            else:
                dump += '.'

        offset += 1

        if offset % 16 == 0:
            if use_ascii:
                print(dump, end = '', file = file)
                dump = ' | '

            print('', file = file)

'''
Base class for exceptions in this module.
'''
class Error(Exception):
    pass

'''
Represents an FTDI device that can be controlled by this utility. A device
consists of an EEPROM that can be read and written as well as a set of
virtual buttons for which press and release events can be simulated.
'''
class Device():
    '''
    Represents a button backed by an I2C register. A specific bit in a given
    register is used to control the status of the button.
    '''
    class I2cButton():
        def __init__(self, port, name, config, output, bit):
            self.name = name
            self.port = port
            self.config = config
            self.output = output
            self.mask = 1 << bit

        def press(self):
            value = self.port.read_from(self.config, 1)
            value[0] &= ~self.mask
            self.port.write_to(self.config, value)

            value = self.port.read_from(self.output, 1)
            value[0] &= ~self.mask
            self.port.write_to(self.output, value)

        def release(self):
            value = self.port.read_from(self.config, 1)
            value[0] |= self.mask
            self.port.write_to(self.config, value)

            value = self.port.read_from(self.output, 1)
            value[0] |= self.mask
            self.port.write_to(self.output, value)

    '''
    Represents a GPIO controller found in FTDI chips. These usually have 8 or
    16 pins. The implementation currently assumes 8 pins.
    '''
    class GpioController():
        '''
        Represents a single pin in the GPIO controller.
        '''
        class Pin():
            def __init__(self, gpio, pin):
                self.gpio = gpio
                self.pin = pin

            def set(self, value):
                self.gpio.set_output(self.pin, value)

        def __init__(self, ftdi):
            self.ftdi = ftdi

            self.direction = 0xf3

            value = self._read()
            value &= 0xf0
            value |= 0x03
            self._write(value)

        def _read(self):
            command = bytes([ Ftdi.GET_BITS_LOW, Ftdi.SEND_IMMEDIATE ])
            self.ftdi.write_data(command)
            data = self.ftdi.read_data_bytes(1, 4)
            return data[0]

        def _write(self, value):
            command = bytes([ Ftdi.SET_BITS_LOW, value, self.direction ])
            self.ftdi.write_data(command)

        def set_output(self, pin, value):
            mask = 1 << (pin % 8)
            self.direction |= mask

            data = self._read()

            if value:
                data &= ~mask
            else:
                data |= mask

            self._write(data)

    class CBUSGpioController:
        class Pin:
            def __init__(self, gpio, pin):
                self.gpio = gpio
                self.pin = pin

                gpio.direction_output(pin)

            def set(self, value):
                self.gpio.set(self.pin, value)

        def __init__(self, ftdi):
            self.ftdi = ftdi
            # default all pins to input
            self.pins = 0x00

        def direction_input(self, pin):
            mask = 1 << pin
            self.pins &= ~(mask << 4)

        def direction_output(self, pin):
            mask = 1 << pin
            self.pins |= mask << 4

        def set(self, pin, value):
            mask = 1 << pin

            # configure pin direction to output
            if not self.pins & (mask << 4):
                print('pin %u is not configured as an output' % pin)
                return

            if not value:
                self.pins &= ~mask
            else:
                self.pins |= mask

            self.ftdi.set_bitmode(self.pins, Ftdi.BITMODE_CBUS)

    '''
    Represents a button backed by a GPIO pin.
    '''
    class GpioButton():
        def __init__(self, gpio, pin, name):
            self.gpio = gpio.Pin(gpio, pin)
            self.name = name

        def press(self):
            self.gpio.set(1)

        def release(self):
            self.gpio.set(0)

    '''
    Represents the EEPROM found on an FTDI chip. This is typically 128 bytes,
    but can be larger or smaller depending on the specific chip.
    '''
    class Eeprom():
        class Descriptor():
            def __init__(self, size):
                self.vendor_id = None
                self.product_id = None
                self.release = None
                self.manufacturer = None
                self.product = None
                self.serial = None
                self.cbus = []

                self.size = size

            def write(self):
                data = bytearray(self.size)

                data[0x00] = 0x88
                data[0x01] = 0x88

                if self.vendor_id:
                    data[0x02] = (self.vendor_id >> 0) & 0xff
                    data[0x03] = (self.vendor_id >> 8) & 0xff

                if self.product_id:
                    data[0x04] = (self.product_id >> 0) & 0xff
                    data[0x05] = (self.product_id >> 8) & 0xff

                if self.release:
                    data[0x06] = (self.release >> 0) & 0xff
                    data[0x07] = (self.release >> 8) & 0xff

                data[0x08] = 0x80
                data[0x09] = 500 >> 1
                data[0x0a] = 0x08
                data[0x0b] = 0x00
                data[0x0c] = 0x00
                data[0x0d] = 0x00

                offset = 0x1a

                if self.manufacturer:
                    data[0x0e] = 0x80 | offset
                    data[0x0f] = len(self.manufacturer) * 2 + 2

                    data[offset + 0] = len(self.manufacturer) * 2 + 2
                    data[offset + 1] = 0x03
                    offset += 2

                    for byte in self.manufacturer.encode('ASCII'):
                        data[offset + 0] = byte
                        data[offset + 1] = 0x00
                        offset += 2

                if self.product:
                    data[0x10] = 0x80 | offset
                    data[0x11] = len(self.product) * 2 + 2

                    data[offset + 0] = len(self.product) * 2 + 2
                    data[offset + 1] = 0x03
                    offset += 2

                    for byte in self.product.encode('ASCII'):
                        data[offset + 0] = byte
                        data[offset + 1] = 0x00
                        offset += 2

                if self.serial:
                    data[0x12] = 0x80 | offset
                    data[0x13] = len(self.serial) * 2 + 2

                    data[offset + 0] = len(self.serial) * 2 + 2
                    data[offset + 1] = 0x03
                    offset += 2

                    for byte in self.serial.encode('ASCII'):
                        data[offset + 0] = byte
                        data[offset + 1] = 0x00
                        offset += 2

                data[offset + 0] = 0x02
                data[offset + 1] = 0x03
                offset += 2

                checksum = Device.Eeprom.checksum(data)
                data[-1] = (checksum >> 8) & 0xff
                data[-2] = (checksum >> 0) & 0xff

                return data

        def __init__(self, ftdi):
            self.ftdi = ftdi

            # XXX parameterize based on chip
            self.size = 128

            self.valid = False
            self.data = []

        @staticmethod
        def parse_string(data, offset, length):
            length = data[offset]
            type = data[offset + 1]

            start = offset + 2
            end = start + length - 2

            return data[start:end:2].decode('ASCII')

        @staticmethod
        def parse(data):
            desc = Device.Eeprom.Descriptor(len(data))

            desc.vendor_id = (data[0x03] << 8) | data[0x02]
            desc.product_id = (data[0x05] << 8) | data[0x04]
            desc.release = (data[0x07] << 8) | data[0x06]

            offset = data[0x0e] & 0x7f
            length = data[0x0f] / 2

            desc.manufacturer = Device.Eeprom.parse_string(data, offset, length)

            offset = data[0x10] & 0x7f
            length = data[0x11] / 2

            desc.product = Device.Eeprom.parse_string(data, offset, length)

            offset = data[0x12] & 0x7f
            length = data[0x13] / 2

            desc.cbus.append(cbus_func(data[0x14] & 0xf))
            desc.cbus.append(cbus_func(data[0x14] >> 4))
            desc.cbus.append(cbus_func(data[0x15] & 0xf))
            desc.cbus.append(cbus_func(data[0x15] >> 4))
            desc.cbus.append(cbus_func(data[0x16] & 0xf))

            desc.serial = Device.Eeprom.parse_string(data, offset, length)

            return desc

        @staticmethod
        def checksum(data):
            checksum = 0xaaaa
            i = 0

            while i < len(data) - 2:
                checksum ^= (data[i + 1] << 8) | data[i]
                checksum &= 0xffff
                checksum = (checksum << 1) | (checksum >> 15)
                checksum &= 0xffff
                i += 2

            return checksum

        def read(self):
            self.data = bytearray()
            self.erased = True

            ep = self.ftdi.usb_dev
            offset = 0

            while offset < self.size / 2:
                data = ep.ctrl_transfer(Ftdi.REQ_IN, Ftdi.SIO_REQ_READ_EEPROM, 0,
                                        offset, 2, self.ftdi._usb_read_timeout)
                if not data:
                    break

                if data[0] != 0xff or data[1] != 0xff:
                    self.erased = False

                self.data.extend(data)
                offset += 1

            checksum = Device.Eeprom.checksum(self.data)
            verify = (data[1] << 8) | data[0]

            if checksum != verify:
                if not self.erased:
                    print('checksum error: expected %04x, got %04x' %
                            (checksum, verify))

                self.valid = False
            else:
                self.valid = True

            return self.data

        def save(self, data, output):
            desc = Device.Eeprom.parse(data)
            output.write(desc.write())

        def write(self, data):
            desc = Device.Eeprom.parse(data)
            ep = self.ftdi.usb_dev
            offset = 0

            checksum = Device.Eeprom.checksum(data)
            verify = (data[-1] << 8) | data[-2]

            if checksum != verify:
                print('checksum error: expected %04x, got %04x' % (checksum, verify))
                sys.exit(1)

            while offset < self.size / 2:
                value = (data[offset * 2 + 1] << 8) | data[offset * 2 + 0]

                ep.ctrl_transfer(Ftdi.REQ_OUT, Ftdi.SIO_REQ_WRITE_EEPROM, value,
                                 offset, 2, self.ftdi.usb_write_timeout)
                offset += 1

        def erase(self):
            ep = self.ftdi.usb_dev

            ep.ctrl_transfer(Ftdi.REQ_OUT, Ftdi.SIO_REQ_ERASE_EEPROM, 0, 0, 0,
                             self.ftdi.usb_write_timeout)

        def show(self, file = sys.stdout):
            desc = Device.Eeprom.parse(self.data)

            print('Vendor: %04x' % desc.vendor_id, file = file)
            print('Product: %04x' % desc.product_id, file = file)
            print('Release: %04x' % desc.release, file = file)

            print('Manufacturer:', desc.manufacturer, file = file)
            print('Product:', desc.product, file = file)
            print('Serial:', desc.serial, file = file)

            print('CBUS:')
            print('  0:', desc.cbus[0])
            print('  1:', desc.cbus[1])
            print('  2:', desc.cbus[2])
            print('  3:', desc.cbus[3])
            print('  4:', desc.cbus[4])

        def dump(self, use_ascii = True, file = sys.stdout):
            hexdump(self.data, use_ascii = use_ascii, file = file)

    class PowerRail():
        def __init__(self, port, name, config, input, bit):
            self.port = port
            self.name = name
            self.config = config
            self.input = input
            self.bit = bit

        def status(self):
            value = self.port.read_from(self.config, 1)
            value[0] |= 0xc0;
            self.port.write_to(self.config, value)

            value = self.port.read_from(self.input, 1)

            if value[0] & 1 << self.bit:
                return False
            else:
                return True

    def __init__(self, ftdi, device, interface):
        self.ftdi = ftdi
        self.device = device
        self.interface = interface

        self.buttons = []
        self.rails = []

    # XXX this is destructive, the device cannot be normally used after this
    def unlock(self):
        self.ftdi.open_from_device(self.device, self.interface)
        self.ftdi.poll_modem_status()
        self.ftdi.set_latency_timer(0x77)

class PM342(Device):
    def __init__(self, ftdi, device, interface):
        super().__init__(ftdi, device, interface)

        self.ftdi.open_mpsse_from_device(device, interface)

        self.gpio = Device.GpioController(self.ftdi)
        self.eeprom = Device.Eeprom(self.ftdi)

        self.i2c = I2cController()
        self.i2c.set_retry_count(1)
        self.i2c.configure(device)

        port = self.i2c.get_port(0x74)

        self.power = Device.I2cButton(port, "power", 0x7, 0x3, 4)
        self.buttons.append(self.power)

        self.reset = Device.I2cButton(port, "reset", 0x6, 0x2, 3)
        self.buttons.append(self.reset)

        self.recovery = Device.I2cButton(port, "recovery", 0x7, 0x3, 3)
        self.buttons.append(self.recovery)

        self.force = Device.GpioButton(self.gpio, 6, "force-off")
        self.buttons.append(self.force)

        self.core = Device.PowerRail(port, "core", 0x7, 0x1, 6)
        self.rails.append(self.core)

        self.cpu = Device.PowerRail(port, "cpu", 0x7, 0x1, 7)
        self.rails.append(self.cpu)

class NanoDebug(Device):
    def __init__(self, ftdi, device, interface):
        super().__init__(ftdi, device, interface)

        self.ftdi.open_bitbang_from_device(device, interface, direction = 0x0,
                                           latency = 16)

        self.gpio = Device.CBUSGpioController(self.ftdi)
        self.eeprom = Device.Eeprom(self.ftdi)

        self.reset = Device.GpioButton(self.gpio, 0, 'reset')
        self.buttons.append(self.reset)

        self.recovery = Device.GpioButton(self.gpio, 1, 'recovery')
        self.buttons.append(self.recovery)

        self.power = Device.GpioButton(self.gpio, 3, 'power')
        self.buttons.append(self.power)

def open(url):
    ftdi = Ftdi()
    desc, interface = ftdi.get_identifiers(url)
    dev = UsbTools.get_device(desc)

    if desc.vid == 0x0403 and desc.pid == 0x6011:
        return PM342(ftdi, dev, interface)

    if desc.vid == 0x0403 and desc.pid == 0x6015:
        return NanoDebug(ftdi, dev, interface)

    raise Exception('Unsupported device %04x:%04x' % (desc.vid, desc.pid))

class Product():
    def __init__(self, descriptor):
        self.vid = descriptor.vid
        self.pid = descriptor.pid
        self.bus = descriptor.bus
        self.address = descriptor.address
        self.serial = descriptor.sn
        self.index = descriptor.index
        self.description = descriptor.description

def find():
    supported = {
            'pm342': ( 0x0403, 0x6011 ),
            'nano': ( 0x0403, 0x6015 )
        }
    vps = supported.values()
    products = []

    for descriptor, interfaces in Ftdi.find_all(vps):
        product = Product(descriptor)

        products.append(product)

    return products

# vim: set et sw=4 sts=4 ts=4:
