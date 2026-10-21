"""Exercise the native shared-memory ABI used across Linux and Wine."""
import os
from pathlib import Path
import shlex
import subprocess
from tempfile import TemporaryDirectory
import unittest

class VolumeStateTest(unittest.TestCase):
    def test_native_reader_invalidates_state_when_speaker_port_changes(self):
        source = Path(__file__).with_name('pulse_port_test.c')
        with TemporaryDirectory(prefix='nahimic-port-test-', dir='/tmp') as directory:
            binary = Path(directory) / 'pulse-port-test'
            flags = subprocess.run(['pkg-config', '--cflags', '--libs', 'libpulse'],
                                   check=True, capture_output=True, text=True).stdout
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) +
                           ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(source),
                            '-o', str(binary)] + shlex.split(flags), check=True)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)

    def test_publication_under_preemption_and_concurrent_access(self):
        source = Path(__file__).with_name('volume_state_test.c')
        with TemporaryDirectory(prefix='nahimic-volume-test-', dir='/tmp') as directory:
            binary = Path(directory) / 'volume-state-test'
            command = shlex.split(os.environ.get('CC', 'cc'))
            subprocess.run(command + ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                                      str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=15)

if __name__ == '__main__': unittest.main()
