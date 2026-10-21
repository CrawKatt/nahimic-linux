"""Keep the disruptive validation script safe to run later, without audio hardware."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import validate_installation as validation


class InstallationValidationTest(unittest.TestCase):
    def test_idle_checks_preserve_dsp_and_restore_controls_even_on_failure(self):
        for fail_volume in (False, True):
            with self.subTest(fail_volume=fail_volume), TemporaryDirectory(dir='/tmp') as directory:
                root=Path(directory)
                (root/'installation.json').write_text('{"target":"speaker"}')
                physical={'name':'speaker','active_port':'analog-output-speaker','mute':True,
                          'properties':{'alsa.components':'HDA:10ec0257,17aa3dcb,00100001'},
                          'volume':{ch:{'value':v} for ch,v in
                                    (('front-left',20000),('front-right',32768))}}
                original=copy.deepcopy(physical)
                state={'enabled':True,'profile':'Music','instance':1}
                profiles={name:{'profile':name,'settings':{'OEM':{'value':index}}}
                          for index,name in enumerate(validation.PROFILES)}
                backend=Mock(spec=validation.Backend)
                backend.status.side_effect=lambda:{'ready':True,'active':False,'applications':0,
                    'enabled':state['enabled'],'instance':state['instance'],'autostart':False,
                    'volume':round(max(validation.level(physical)[0])/65536*100),'muted':physical['mute']}
                backend.settings.side_effect=lambda:copy.deepcopy(profiles[state['profile']])
                backend.enabled.side_effect=lambda enabled:state.update(enabled=enabled)
                def control(option, guid):
                    self.assertEqual(option,'--profile')  # Never force global mode or write DSP.
                    state['profile']=next(n for n,(_,g) in validation.PROFILES.items() if '{'+g+'}'==guid)
                backend.control.side_effect=control
                def pulse(*args):
                    if args[:2]==('--format=json','list'):
                        return json.dumps([physical] if args[2]=='sinks' else [])
                    self.assertEqual(args[1],'speaker')  # The virtual sink stays untouched.
                    if args[0]=='set-sink-volume':
                        for ch,value in zip(('front-left','front-right'),args[2:]):
                            physical['volume'][ch]['value']=int(value)
                    elif args[0]=='set-sink-mute':physical['mute']=bool(int(args[2]))
                    else:self.fail(str(args))
                def volume(value):
                    for channel in physical['volume'].values():channel['value']=round(value/100*65536)
                    if fail_volume:raise RuntimeError('simulated volume failure')
                backend.volume.side_effect=volume
                backend.mute.side_effect=lambda value:physical.update(mute=value)
                def restart(command, **kwargs):
                    self.assertEqual(command,['systemctl','--user','restart','nahimic.service'])
                    state['instance']+=1
                def wait(predicate,label,timeout=40):
                    self.assertTrue(predicate(),label)  # In particular, idle active=False must pass.
                with patch.object(validation,'Backend',return_value=backend), \
                     patch.object(validation,'RUNTIME',root/'runtime'), \
                     patch.object(validation,'pulse',side_effect=pulse), \
                     patch.object(validation,'wait',side_effect=wait), \
                     patch.object(validation.tempfile,'mkdtemp',return_value=directory), \
                     patch.object(validation.subprocess,'run',side_effect=restart) as run, \
                     patch('builtins.print'):
                    if fail_volume:
                        with self.assertRaisesRegex(RuntimeError,'simulated volume failure'):validation.main()
                    else:validation.main()
                backend.set_setting.assert_not_called()
                self.assertEqual(physical,original)
                self.assertTrue(state['enabled'])
                self.assertEqual(state['profile'],'Music')
                self.assertEqual(run.call_count,0 if fail_volume else 2)
                results=json.loads((root/'results.json').read_text())
                self.assertEqual(bool(results.get('passed')),not fail_volume)

    def test_live_playback_or_recording_refuses_disruptive_checks(self):
        for kind in ('sink-inputs','source-outputs'):
            backend=Mock(spec=validation.Backend)
            backend.status.return_value={'ready':True}
            def pulse(*args):
                return json.dumps([{'corked':False,'properties':{'node.name':'call'}}] if args[-1]==kind else [])
            with patch.object(validation,'Backend',return_value=backend), \
                 patch.object(validation,'pulse',side_effect=pulse), self.assertRaises(RuntimeError):
                validation.main()
            backend.enabled.assert_not_called()
            backend.control.assert_not_called()


if __name__=='__main__':unittest.main()
