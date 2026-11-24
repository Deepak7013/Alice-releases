
"""Alice-native style profiles and reusable document recipes."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class StyleProfile:
    name:str="alice_clean"
    font:str="Aptos"
    accent:str="2F5597"
    title_size:int=28
    heading_size:int=16
    body_size:int=11
    compact:bool=False

BUILTINS={
 "alice_clean":StyleProfile(),
 "academic":StyleProfile("academic","Aptos","1F4E79",26,15,11,False),
 "business":StyleProfile("business","Aptos Display","1F1F1F",30,17,10,True),
 "minimal":StyleProfile("minimal","Aptos","666666",24,14,10,True),
}

def resolve_style(name="alice_clean", custom=None):
    base=BUILTINS.get(name,BUILTINS["alice_clean"])
    if not custom:return base
    data=base.__dict__.copy(); data.update(dict(custom)); return StyleProfile(**data)
