"""Select each OEM set without crossing hardware identities or saved sessions."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
from desktop_audio import speaker_config, supported_speaker
from entry import detect
from run_local import main, validate_session

MECHREVO = {'name': 'speaker', 'active_port': '[Out] Speaker',
            'properties': {'alsa.components': 'HDA:14f11f87,1d05e022,00100100'}}
MECHREVO_P916F = {'name': 'speaker', 'active_port': '[Out] Speaker',
                 'properties': {'alsa.components': 'HDA:10ec0256,1d05e004,00100002'}}
LENOVO = {'name': 'speaker', 'active_port': 'analog-output-speaker',
          'properties': {'alsa.components': 'HDA:10ec0257,17aa3dcb,00100001 HDA:80862818,80860101,00100000'}}
CASES = ((MECHREVO, '.', '1D05E022_Speakers.nsx'),
         (MECHREVO_P916F, '.', '1D05E004_InternalSpeakers.nsx'),
         (LENOVO, '17AA3DCB', '17AA3DCB_InternalSpeakers.nsx'))


class DeviceTest(unittest.TestCase):
    def test_exact_codec_subsystem_and_speaker_ports(self):
        for sink, directory, filename in CASES:
            with self.subTest(device=filename):
                self.assertEqual(speaker_config(sink), (directory, filename))
                for port in ('[Out] Speaker', 'analog-output-speaker'):
                    variant = copy.deepcopy(sink)
                    variant['active_port'] = port
                    variant['properties']['alsa.components'] = variant['properties']['alsa.components'].upper()
                    self.assertTrue(supported_speaker(variant))
                for port in ('[Out] Headphones', 'analog-output-headphones', 'hdmi-output-0', None):
                    self.assertFalse(supported_speaker(sink | {'active_port': port}))
        for components in ('HDA:10ec0257,17aa382b,00100001', 'HDA:10ec0257,17aa3dcc,00100001',
                           'HDA:14f11f87,17aa3dcb,00100001', 'HDA:10ec0295,17aa3dcb,00100001',
                           'USB1234:5678', 'prefixHDA:10ec0257,17aa3dcb,00100001', ''):
            self.assertFalse(supported_speaker(LENOVO | {'properties': {'alsa.components': components}}))
        self.assertFalse(supported_speaker({}))

    def test_detection_requires_one_supported_endpoint(self):
        for sink, _, _ in CASES:
            with patch('entry.pulse', return_value=json.dumps([sink, {'name': 'hdmi'}])):
                self.assertEqual(detect(), 'speaker')
        for sinks in ([], [MECHREVO, LENOVO], [MECHREVO, MECHREVO_P916F]):
            with patch('entry.pulse', return_value=json.dumps(sinks)), self.assertRaises(RuntimeError):
                detect()

    def test_saved_sessions_preserve_each_device_and_reject_other_hardware(self):
        for sink, _, _ in CASES:
            saved = {'settings_initialized': True, 'target': sink['name'],
                     'target_before': sink, 'original_dll_sha256': 'original'}
            validate_session(saved, sink, 'original')  # Also accepts the pre-change session format.
            for other, _, _ in CASES:
                if other == sink:
                    continue
                with self.assertRaises(ValueError):
                    validate_session(saved, other, 'original')
            for field, value in (('settings_initialized', False), ('target', 'another'),
                                 ('target_before', {}), ('original_dll_sha256', 'different')):
                with self.assertRaises(ValueError):
                    validate_session(saved | {field: value}, sink, 'original')

    def test_launcher_delivers_only_selected_oem_settings_to_host(self):
        class BeforeAudio(Exception):
            pass

        with tempfile.TemporaryDirectory(prefix='nahimic-devices-', dir='/tmp') as directory:
            root = Path(directory)
            for executable in ('apo_probe.exe', 'NahimicAPO4.dll', 'pulse_state'):
                (root / executable).touch()
            for index, (_, folder, filename) in enumerate(CASES):
                factory = root / 'factory' / folder
                (factory / 'Devices').mkdir(parents=True, exist_ok=True)
                (factory / 'AudioProfiles').mkdir(exist_ok=True)
                (factory / 'Global.nsx').write_text('<nhSettings><Settings/></nhSettings>')
                (factory / 'Metadata.nsx').write_text('<nhSettings><Data><DefaultProfileId>'
                    '<Value>music</Value></DefaultProfileId></Data></nhSettings>')
                (factory / 'Devices' / filename).write_text('<nhSettings><Data><ID>'
                    f'<Value>device-{index}</Value></ID></Data></nhSettings>')
                (factory / 'AudioProfiles/Music.nsx').write_text('<nhSettings>'
                    f'<Settings><OEM Value="{folder}"/></Settings>'
                    '<Data><ID><Value>music</Value></ID></Data></nhSettings>')
            for index, (sink, folder, filename) in enumerate(CASES):
                work = root / f'state-{index}'
                work.mkdir()
                (work / '.nahimic-session').write_text('nahimic-linux-v1\n')
                command = ['run_local.py', '--exe', str(root / 'apo_probe.exe'),
                           '--dll', str(root / 'NahimicAPO4.dll'), '--settings', str(root / 'factory'),
                           '--target', sink['name'], '--state-dir', str(work)]

                def start(args, **kwargs):
                    if args[0] == str(root / 'pulse_state'):
                        self.assertEqual(args[3], sink['active_port'])
                        kwargs['stderr'].write(b'volume_state_ready\n')
                        kwargs['stderr'].flush()
                        return SimpleNamespace(poll=lambda: 0, wait=lambda **kw: 0, returncode=0)
                    self.assertEqual(args[args.index('--device-file') + 1], filename)
                    self.assertEqual(args[args.index('--device-id') + 1], f'device-{index}')
                    raise BeforeAudio()

                with patch('sys.argv', command), patch('run_local.signal.signal'), \
                     patch('run_local.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps([sink]))), \
                     patch('run_local.subprocess.Popen', side_effect=start), self.assertRaises(BeforeAudio):
                    main()
                prepared = work / 'settings'
                factory = root / 'factory' / folder
                device_files = {p.name for p in (factory / 'Devices').iterdir()}
                self.assertEqual({p.name for p in (prepared / 'Devices').iterdir()}, device_files)
                self.assertEqual((prepared / 'AudioProfiles/Music.nsx').read_bytes(),
                                 (factory / 'AudioProfiles/Music.nsx').read_bytes())
                manifest = json.loads((prepared / 'source-manifest.json').read_text())
                self.assertEqual(set(manifest['originals']),
                                 {'Global.nsx', 'Metadata.nsx', 'AudioProfiles/Music.nsx'} |
                                 {f'Devices/{name}' for name in device_files})
                self.assertEqual(manifest['originals'][f'Devices/{filename}'],
                                 hashlib.sha256((factory / 'Devices' / filename).read_bytes()).hexdigest())


if __name__ == '__main__': unittest.main()
