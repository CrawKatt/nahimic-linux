"""Exercise installed controls/restarts with playback stopped, or take a read-only snapshot."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from backend import Backend, PROFILES, RUNTIME
from desktop_audio import pulse, level, supported_speaker


def wait(predicate, label, timeout=40):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        result=predicate()
        if result:return result
        time.sleep(.15)
    raise TimeoutError(label)


def snapshot():
    b=Backend();status=b.status()
    session=json.loads((RUNTIME/'session.json').read_text())
    return {'status':status, 'settings':b.settings() if status.get('ready') else None,
            'session':{k:session.get(k) for k in ('device_id','device_file','original_dll_sha256','reused_settings')},
            'default_sink':pulse('get-default-sink'),
            'sinks':json.loads(pulse('--format=json','list','sinks')),
            'sink_inputs':json.loads(pulse('--format=json','list','sink-inputs'))}


def main():
    b=Backend();before=b.status()
    streams=[s for kind in ('sink-inputs','source-outputs')
             for s in json.loads(pulse('--format=json','list',kind))]
    if not before.get('ready') or any(not s.get('corked',False) and
            s.get('properties',{}).get('node.name') not in
            ('nahimic_speakers_render','nahimic_speakers_capture') for s in streams):
        raise RuntimeError('Run with the service ready, playback stopped and calls/recording closed')
    original=b.settings()
    work=Path(tempfile.mkdtemp(prefix='nahimic-install-check-',dir='/tmp'))
    print(work,flush=True)
    results={};(work/'before.json').write_text(json.dumps({'status':before,'settings':original},indent=2)+'\n')
    target=json.loads((RUNTIME.parent/'installation.json').read_text())['target']
    def physical():
        data={s['name']:s for s in json.loads(pulse('--format=json','list','sinks'))}
        return data[target]
    def profile(name):
        # --profile retains the current global/application mode.
        b.control('--profile','{'+PROFILES[name][1]+'}')
        state=b.settings()
        assert state['profile']==name
        return state
    def enabled(value):
        b.enabled(value)
        wait(lambda:b.status().get('enabled')==value and not b.status().get('active'),'idle enable/bypass')
    def restore_volume():
        pulse('set-sink-volume',target,*(str(v) for v in level(initial_physical)[0]))
        pulse('set-sink-mute',target,str(int(initial_physical['mute'])))
    initial_physical=physical()
    if not supported_speaker(initial_physical):
        raise RuntimeError('The configured output must be the supported built-in speakers')
    try:
        enabled(False)
        results['profiles']={name:profile(name) for name in PROFILES}
        assert profile(original['profile'])==original
        volume=max(0,before['volume']-2) if before['volume'] else 2
        b.volume(volume)
        wait(lambda:b.status().get('volume')==volume and
             round(max(level(physical())[0])/65536*100)==volume,'panel volume -> hardware')
        for muted in (True,False):
            b.mute(muted)
            wait(lambda:physical()['mute']==muted and b.status().get('muted')==muted,'panel mute -> hardware')
        restore_volume()
        wait(lambda:level(physical())==level(initial_physical) and
             b.status().get('volume')==before['volume'] and
             b.status().get('muted')==before['muted'],'hardware volume/mute -> panel')
        results['real_volume_and_mute']=True
        for value in (False,True)*5:
            enabled(value)
        results['bypass_cycles']=5
        expected=profile('Movie')
        for value in (False,True):
            enabled(value)
            old_pid=b.status()['instance']
            subprocess.run(['systemctl','--user','restart','nahimic.service'],check=True,timeout=40)
            wait(lambda:b.status().get('ready') and b.status().get('instance')!=old_pid,'cold restart')
            assert b.settings()==expected
            assert b.status()['enabled']==value and not b.status()['active']
        assert {name:profile(name) for name in PROFILES}==results['profiles']
        results['profiles_parameters_and_enable_survive_restart']=True
        assert b.status()['autostart']==before['autostart']
        results['passed']=True
    finally:
        for restore in (lambda:profile(original['profile']),lambda:b.enabled(before['enabled']),restore_volume):
            try:restore()
            except Exception as error:
                results.setdefault('restoration_errors',[]).append(str(error))
        if results.get('restoration_errors'):results['passed']=False
        (work/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps(results),flush=True)
        if results.get('restoration_errors'):raise RuntimeError('Restoration failed; see '+str(work/'results.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',action='store_true',help='Read status/settings/routing without changing audio')
    if parser.parse_args().snapshot:print(json.dumps(snapshot(),indent=2))
    else:main()
