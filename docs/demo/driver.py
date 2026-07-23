#!/usr/bin/env python3
"""Drives the create-tess interactive wizard through a fixed, scripted set of
answers, over a real pty, passing through all raw output unmodified so an
outer terminal-recorder (asciinema) captures the genuine session. Pattern
matching for "when do I send the next keystroke" strips ANSI codes from an
internal copy of the buffer only -- the passthrough to stdout is untouched.
"""
import os
import pty
import re
import sys
import time
import select
import fcntl
import termios
import struct

ANSI_RE = re.compile(rb'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][A-Za-z0-9]')

STEPS = [
    (b'framed', b'\r'),          # S1 vibe select -> first option (Guild Path / rpg)
    (b'call you', b'Avery\r'),   # S2 operator name
    (b'excellent', b'\r'),       # S3 starter path select -> first option (founders)
    (b'keep Tess', b'\r'),       # S4 conductor name -> default "Tess"
    (b'in the room', b'\r'),     # S5 pathway select -> first option (chief-of-staff)
    (b'Telegram now', b'n\r'),   # S6 telegram confirm -> skip
    (b'the gates', b'\r'),       # S7 recap confirm -> proceed
]


def main():
    target_cmd = sys.argv[1:]
    if not target_cmd:
        print('usage: driver.py <cmd> [args...]', file=sys.stderr)
        sys.exit(2)

    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(target_cmd[0], target_cmd)
        os._exit(127)

    # CRITICAL: pty.fork() leaves the pty with no window size set (0x0),
    # which makes width-sensitive TUI rendering (box borders, wrapping)
    # break -- observed as every character landing on its own line. Set a
    # real size immediately so the child renders exactly as a normal
    # terminal would.
    winsize = struct.pack('HHHH', 30, 100, 0, 0)  # rows, cols, xpixel, ypixel
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    step_idx = 0
    buf = b''
    last_data_at = time.time()
    start = time.time()

    while True:
        if time.time() - start > 90:
            sys.stderr.write('\n[driver] overall timeout exceeded, aborting\n')
            break
        try:
            r, _, _ = select.select([fd], [], [], 0.2)
        except OSError:
            break
        if fd in r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            os.write(1, data)
            buf += data
            last_data_at = time.time()
            clean = ANSI_RE.sub(b'', buf).replace(b'\r', b'')
            if step_idx < len(STEPS):
                pattern, keys = STEPS[step_idx]
                if pattern in clean:
                    time.sleep(0.5)
                    os.write(fd, keys)
                    step_idx += 1
                    buf = b''
        else:
            if time.time() - last_data_at > 12 and step_idx < len(STEPS):
                sys.stderr.write(f'\n[driver] no output for 12s waiting on step {step_idx} '
                                  f'({STEPS[step_idx][0]!r}), aborting\n')
                break
            try:
                wpid, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                break
            if wpid != 0:
                break

    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


if __name__ == '__main__':
    main()
