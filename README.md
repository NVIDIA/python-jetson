Jetson Control Utility
======================

The purpose of this utility is to let users control NVIDIA Jetson boards
for automation. It talks to the Jetson boards via an FTDI chip integrated
on some developer kit baseboards. Refer to developer kit documentation to
determine if your developer kit or baseboard supports this feature.

This utility has been validated on the following platforms:
- Jetson AGX Xavier

Dependencies
------------

The Jetson control utility is written for Python 3 and doesn't implement
backwards compatibility with Python 2. It primarily relies on the Python
standard library, but uses the pyftdi library to communicate with FTDI
chips. You can obtain pyftdi from [Pypi](https://pypi.org/project/pyftdi)
or [Github](http://github.com/eblot/pyftdi).

Most distributions don't provide a package for pyftdi, unfortunately, so
you'll have to manually install it using pip:

```
$ pip install pyftdi
```

Alternatively, use your preferred method to install pyftdi.

Usage
-----

``jetson-control`` will use the first available FTDI chip that can be found.
There is also a mechanism to pick a specific instance identified by its
serial number.

Each invocation of ``jetson-control`` executes a single command, which makes
it well suited for scripting.

Commands
--------

To find out which devices exist on a system run the ``devices`` command.
It lists all the compatible devices found on the USB bus.

Buttons can be controlled using the ``press`` and ``release`` commands,
each of which take the name of the button to control as a parameter.

The following buttons are defined:

* ``power``: press to power up the device, press and hold for 10
  seconds to force power off
* ``reset``: pressing this button puts the device into reset, release to
  boot
* ``recovery``: must be pressed before the ``reset`` button is released
  or when the ``power`` button is pressed in order to enter recovery
  mode
* ``force-off``: forces the device off immediately

The utility supports reading, writing and erasing the EEPROM using the
``eeprom`` command. Several sub-commands are available, such as ``read``
to save the EEPROM contents into a file, specified as an argument,
``write`` to flash the contents of a file, specified as an argument, or
``erase`` to erase the EEPROM. The ``dump`` and ``show`` commands can be
used to read the EEPROM and show a hexdump or a decoded version,
respectively.

Some boards support querying the state of the core and the CPU power
rails. This can be done using the ``power-rail`` command. An optional
argument can be used to specify the name of the rail to query. If no
value is specified, the status for all power rails will be shown.
