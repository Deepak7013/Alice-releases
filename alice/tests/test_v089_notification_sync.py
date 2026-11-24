from alice.android.notification_sync import AndroidNotificationSync
from alice.android.notifications import NotificationMirror
class A:
    def shell(self,d,c): return "com.test | Title | Hello\ncom.other | Other | World"
def test_sync(tmp_path):
    m=NotificationMirror(tmp_path); n=AndroidNotificationSync(A(),m)
    assert n.sync("abc")["synced"]==2
    assert len(m.list())==2
def test_filter(tmp_path):
    m=NotificationMirror(tmp_path); n=AndroidNotificationSync(A(),m)
    assert n.sync("abc","com.test")["synced"]==1
