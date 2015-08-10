vmchatinput
===========

Scripts for piping IRC chat from TwitchPlaysPokemon into Windows 98 via VirtualBox. The chat triggers keystrokes and mouse movements that controls Windows. No, this isn't affiliated with TPP, and yes, TPP is still a thing.


Quick Start
===========

You will need:

* Linux (tested in Ubuntu 15.04)
* VirtualBox (tested with 4.3)
* Python 2.7
* pngcrush
* xz

Python packages:

* pyvbox (0.2.2)
* irc (12.3)
* pillow (2.7)

1. Install VirtualBox from their website.
2. Install stable packages: `sudo apt-get install python-pil pngcrush xz-utils`
3. Install latest Python packages: `pip2 install irc pyvbox --user`
4. Set up your Windows 98 install following [these instructions](https://forums.virtualbox.org/viewtopic.php?t=9918). The CD can be found using the magnet `c36f60c0dc13976f44037eb56d11ee943f471c93`. The driver registration key can be found [here](https://scitechdd.wordpress.com/).
5. Edit the example JSON config file.
6. Run `python2 run_forever.py`

* Screenshots and logging will be placed in the log directory specified. They will be compressed once the day has passed.
* `run_forever.py` will attempt to restart the scripts if they error.
* The virtual machine is rebooted if it errors or it appears frozen.


Credits
=======

Copyright 2015 Christopher Foo. License: MIT.


