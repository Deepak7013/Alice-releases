from alice.messaging.whatsapp import WhatsAppReader,WhatsAppAccessError

def test_whatsapp_never_fakes_live_access():
 try: WhatsAppReader().open('phone'); assert False
 except WhatsAppAccessError: pass
