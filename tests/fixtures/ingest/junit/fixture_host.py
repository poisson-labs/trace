"""A pytest plugin for making the JUnit fixture: the report names its host as ``localhost``.

pytest writes the machine's name (``platform.node()``) into the report's ``hostname``
attribute; this plugin, loaded with ``-p fixture_host``, gives it ``localhost`` instead, so
the committed reports are what pytest wrote and name no machine. It changes nothing else.
"""

import platform

platform.node = lambda: "localhost"
