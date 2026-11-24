from alice.android.notifications import NotificationMirror

def test_notification_mirror_filters_and_persists(tmp_path):
 n=NotificationMirror(tmp_path); x=n.ingest('com.whatsapp','Bob','hello'); assert n.list('com.whatsapp',True)[0]['id']==x['id']; n.mark_read(x['id']); assert n.list('com.whatsapp',True)==[]
