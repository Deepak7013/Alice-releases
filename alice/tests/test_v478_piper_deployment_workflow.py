def test_preflight_failure_never_calls_runtime():
 calls=[]
 def preflight(*a,**k): return {'ready_for_runtime_test':False,'reason':'not_ready'}
 def runtime(*a,**k): calls.append(1); return {'passed':True}
 from alice.voice.piper_deployment_workflow import run_guided_piper_check
 r=run_guided_piper_check('c','r',confirm_female=True,preflight=preflight,runtime_diagnostic=runtime,platform_name='Windows')
 assert not r['passed'] and r['runtime'] is None and not calls
def test_missing_female_confirmation_never_calls_runtime():
 calls=[]
 def preflight(*a,**k): return {'ready_for_runtime_test':True}
 def runtime(*a,**k): calls.append(1); return {'passed':True}
 from alice.voice.piper_deployment_workflow import run_guided_piper_check
 r=run_guided_piper_check('c','r',preflight=preflight,runtime_diagnostic=runtime,platform_name='Windows')
 assert r['reason']=='female_profile_confirmation_required' and not calls
def test_successful_preflight_and_confirmation_runs_piper_only_test():
 calls=[]
 def preflight(*a,**k): return {'ready_for_runtime_test':True}
 def runtime(*a,**k): calls.append((a,k)); return {'passed':True,'reason':'piper_synthesis_and_playback_passed'}
 from alice.voice.piper_deployment_workflow import run_guided_piper_check
 r=run_guided_piper_check('c','r',confirm_female=True,preflight=preflight,runtime_diagnostic=runtime,platform_name='Windows')
 assert r['passed'] and r['reason']=='piper_runtime_test_passed' and len(calls)==1
def test_runtime_failure_is_not_masked_by_successful_preflight():
 def preflight(*a,**k): return {'ready_for_runtime_test':True}
 def runtime(*a,**k): return {'passed':False,'reason':'piper_synthesis_or_playback_failed'}
 from alice.voice.piper_deployment_workflow import run_guided_piper_check
 r=run_guided_piper_check('c','r',confirm_female=True,preflight=preflight,runtime_diagnostic=runtime,platform_name='Windows')
 assert not r['passed'] and r['reason']=='piper_runtime_test_failed'
