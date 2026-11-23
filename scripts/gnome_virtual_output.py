#!/usr/bin/python3
"""Hold one fixed GNOME virtual output only when the login has no logical display."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

import gi
from gi.repository import Gio, GLib

try:
    gi.require_version("GLibUnix", "2.0")
    from gi.repository import GLibUnix
    unix_signal_add = GLibUnix.signal_add
except (AttributeError, ImportError, ValueError):
    unix_signal_add = GLib.unix_signal_add


CAST = "org.gnome.Mutter.ScreenCast"
SESSION = CAST + ".Session"
DISPLAY = "org.gnome.Mutter.DisplayConfig"
STARTUP_SECONDS = 8.0
UNIT = "xuexitong-virtual-output"


class StartupFailure(RuntimeError):
    pass


def object_path(interface):
    return "/" + interface.replace(".", "/")


def announce(state, *, notify=True):
    address = os.environ.get("NOTIFY_SOCKET") if notify else None
    if address:
        if address.startswith("@"):
            address = "\0" + address[1:]
        status = "Using existing logical display" if state == "native" else "Virtual logical display ready"
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
            notifier.settimeout(0.5)
            notifier.connect(address)
            notifier.sendall(f"READY=1\nSTATUS={status}".encode("ascii"))
    print(json.dumps({"state": state}), flush=True)


def hold_output(*, probe=False, connect=Gio.bus_get_sync, report=announce):
    deadline = time.monotonic() + STARTUP_SECONDS
    cancel = Gio.Cancellable()
    startup_timer = threading.Timer(STARTUP_SECONDS, cancel.cancel)
    startup_timer.daemon = True
    loop = GLib.MainLoop()
    bus = session = subscription = None

    def stop(*_):
        cancel.cancel()
        loop.quit()
        return GLib.SOURCE_CONTINUE

    signal_sources = [unix_signal_add(GLib.PRIORITY_HIGH, sig, stop)
                      for sig in (signal.SIGTERM, signal.SIGINT)]

    def call(name, path, interface, method, args=None):
        # Process a queued termination request even during synchronous setup.
        context = loop.get_context()
        while context.pending():
            context.iteration(False)
        remaining = deadline - time.monotonic()
        if remaining <= 0 or cancel.is_cancelled():
            raise StartupFailure("startup interrupted or timed out")
        try:
            return bus.call_sync(name, path, interface, method, args, None,
                                 Gio.DBusCallFlags.NO_AUTO_START, max(1, int(remaining * 1000)), cancel)
        except GLib.Error as error:
            raise StartupFailure(f"{method} unavailable, denied, or timed out") from error

    def logical_count():
        state = call(DISPLAY, object_path(DISPLAY), DISPLAY, "GetCurrentState").unpack()
        if len(state) != 4 or not isinstance(state[2], (tuple, list)):
            raise StartupFailure("unexpected logical-display reply")
        return len(state[2])

    def session_closed(*_):
        stop()

    startup_timer.start()
    try:
        bus = connect(Gio.BusType.SESSION, cancel)
        initial = logical_count()
        if probe:
            report("native" if initial else "absent", notify=False)
            return
        if initial:
            report("native")
            return

        session = call(CAST, object_path(CAST), CAST, "CreateSession", GLib.Variant("(a{sv})", ({},))).unpack()[0]
        modes = GLib.Variant("aa{sv}", [{
            "size": GLib.Variant("(uu)", (1280, 800)),
            "refresh-rate": GLib.Variant("d", 60.0),
            "is-preferred": GLib.Variant("b", True),
        }])
        props = {"modes": modes, "cursor-mode": GLib.Variant("u", 0)}
        call(CAST, session, SESSION, "RecordVirtual", GLib.Variant("(a{sv})", (props,)))
        if logical_count():
            report("native")
            return

        subscription = bus.signal_subscribe(CAST, SESSION, "Closed", session, None,
                                            Gio.DBusSignalFlags.NONE, session_closed)
        bus.connect("closed", session_closed)
        call(CAST, session, SESSION, "Start")
        count = logical_count()
        while count == 0:
            time.sleep(0.1)
            count = logical_count()
        if count > 1:
            # An RDP viewer may have reconnected in the brief interval around
            # Start. Drop only this helper's output before reporting native.
            call(CAST, session, SESSION, "Stop")
            session = None
            if not logical_count():
                raise StartupFailure("concurrent logical display went away")
            report("native")
            return

        startup_timer.cancel()
        if cancel.is_cancelled():
            raise StartupFailure("startup interrupted or timed out")
        report("ready")
        loop.run()
    finally:
        startup_timer.cancel()
        for source in signal_sources:
            GLib.source_remove(source)
        if bus is not None:
            if subscription is not None:
                bus.signal_unsubscribe(subscription)
            if session is not None and not bus.is_closed():
                try:
                    bus.call_sync(CAST, session, SESSION, "Stop", None, None,
                                  Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
                except GLib.Error:
                    # Leaving this process closes its unique D-Bus peer too.
                    pass


def probe_output():
    states = []
    hold_output(probe=True, report=lambda state, **_: states.append(state))
    return states[0]


def ensure_output():
    if probe_output() == "native":
        announce("native", notify=False)
        return

    # The user manager keeps this display alive after the opener exits. If two
    # profiles start together they share this single unit and one virtual output.
    command = ["systemd-run", "--user", "--collect", "--quiet", f"--unit={UNIT}",
               "--property=Type=notify", "--property=TimeoutStartSec=10s", "--",
               sys.executable, "-B", str(Path(__file__).resolve())]
    subprocess.run(command, capture_output=True, timeout=14)
    # Starting an already-running unit can return nonzero; only a real logical
    # output (possibly from a concurrent desktop reconnect) satisfies the opener.
    if probe_output() != "native":
        raise StartupFailure("GNOME still has no logical display")
    announce("ready", notify=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe", action="store_true", help="Read logical display state without creating an output")
    mode.add_argument("--ensure", action="store_true", help="Ensure an output before launching Chrome in this login")
    options = parser.parse_args()
    try:
        if options.ensure:
            ensure_output()
        else:
            hold_output(probe=options.probe)
    except (StartupFailure, GLib.Error, OSError, subprocess.TimeoutExpired) as error:
        reason = str(error) if isinstance(error, StartupFailure) else type(error).__name__
        print(json.dumps({"state": "error", "reason": reason}), flush=True)
        raise SystemExit(1)
