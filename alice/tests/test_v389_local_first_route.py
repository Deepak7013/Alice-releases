from alice.engineering.local_first_route import choose_route
def test_verified_local_wins(): assert choose_route('engineering',True,True,True).route=='local'
def test_external_requires_allowance():
 assert choose_route('engineering',False,False,False).route=='blocked_unverified'
 assert choose_route('engineering',False,False,True).route=='external'
def test_unverified_local_does_not_win(): assert choose_route('engineering',True,False,False).route=='blocked_unverified'
