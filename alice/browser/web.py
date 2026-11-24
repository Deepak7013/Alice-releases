import requests
from bs4 import BeautifulSoup

def fetch(url):
    r=requests.get(url,timeout=20,headers={"User-Agent":"Alice/0.5"})
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    return soup.get_text(" ",strip=True)[:30000]
