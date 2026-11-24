from alice.android.adb import ADBAdapter

def test_adb_adapter_is_safe_wrapper():
 a=ADBAdapter('missing-adb');
 try:a.devices(); assert False
 except Exception as e: assert 'missing-adb' in str(e) or e.__class__.__name__=='ADBError'
