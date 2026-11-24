"""Lightweight internet research for Alice. Search results are treated as untrusted data."""
import re
import ipaddress
import socket
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlparse
import requests
from bs4 import BeautifulSoup

class WebResearch:
    MAX_PAGE_BYTES = 2 * 1024 * 1024
    MAX_REDIRECTS = 4
    REDIRECT_CODES = {301, 302, 303, 307, 308}

    def __init__(self, timeout=15): self.timeout=timeout

    @staticmethod
    def _validate_public_url(url):
        """Reject non-public targets before fetching search-result URLs."""
        if not isinstance(url, str) or not re.match(r"^https?://", url, re.I):
            raise ValueError("Only HTTP(S) URLs are allowed")
        parsed=urlparse(url)
        if (not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 80, 443)):
            raise ValueError("URL must have a public host and a standard HTTP(S) port")
        host=parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Private or local network URLs are not allowed")
        try:
            literal=ipaddress.ip_address(host)
            addresses=[literal]
        except ValueError:
            try:
                addresses=[ipaddress.ip_address(row[4][0])
                           for row in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                                        type=socket.SOCK_STREAM)]
            except OSError as exc:
                raise ValueError("URL host could not be resolved") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("Private or non-public network addresses are not allowed")
        return url

    def _get_public_page(self, url):
        """Fetch bounded HTML/text, validating each redirect destination."""
        current=self._validate_public_url(url)
        for redirect_count in range(self.MAX_REDIRECTS + 1):
            response=requests.get(current,headers={"User-Agent":"Mozilla/5.0 Alice/0.11"},
                                  timeout=self.timeout,allow_redirects=False,stream=True)
            headers=getattr(response,"headers",{})
            if getattr(response,"status_code",200) in self.REDIRECT_CODES:
                location=headers.get("Location")
                close=getattr(response,"close",lambda:None); close()
                if not location or redirect_count >= self.MAX_REDIRECTS:
                    raise requests.TooManyRedirects("Too many or invalid redirects")
                current=self._validate_public_url(urljoin(current,location))
                continue
            response.raise_for_status()
            content_type=headers.get("Content-Type", "").lower()
            if content_type and not any(kind in content_type for kind in ("text/", "html", "xml")):
                getattr(response,"close",lambda:None)()
                raise ValueError("Source response is not a text or HTML page")
            length=headers.get("Content-Length")
            if length and length.isdigit() and int(length) > self.MAX_PAGE_BYTES:
                getattr(response,"close",lambda:None)()
                raise ValueError("Source page exceeds the 2 MiB fetch limit")
            chunks=[]; size=0
            try:
                iterator=(response.iter_content(chunk_size=64 * 1024)
                          if hasattr(response,"iter_content")
                          else [getattr(response,"text","").encode("utf-8")])
                for chunk in iterator:
                    if not chunk:
                        continue
                    size+=len(chunk)
                    if size > self.MAX_PAGE_BYTES:
                        raise ValueError("Source page exceeds the 2 MiB fetch limit")
                    chunks.append(chunk)
            finally:
                getattr(response,"close",lambda:None)()
            # Pass raw bytes to BeautifulSoup so it can honor HTML charset
            # declarations and avoid mojibake from incorrect HTTP headers.
            return b"".join(chunks), current
        raise requests.TooManyRedirects("Too many redirects")

    @staticmethod
    def _google_results(html, max_results):
        soup=BeautifulSoup(html,"html.parser")
        out=[]; seen=set()
        for a in soup.select('a'):
            h=a.select_one('h3')
            if not h: continue
            href=a.get('href','')
            m=re.search(r'https?://[^&]+',href)
            if not m: continue
            target=m.group(0)
            if target in seen: continue
            seen.add(target)
            out.append({"title":h.get_text(" ",strip=True),"url":target,"snippet":a.parent.get_text(" ",strip=True)[:500]})
            if len(out)>=max_results: break
        return out

    @staticmethod
    def _duckduckgo_results(html, max_results):
        soup=BeautifulSoup(html,"html.parser")
        out=[]; seen=set()
        for a in soup.select('a.result__a'):
            href=str(a.get('href','')).strip()
            parsed=urlparse(urljoin('https://html.duckduckgo.com',href))
            if parsed.hostname and parsed.hostname.lower().endswith('duckduckgo.com'):
                target=(parse_qs(parsed.query).get('uddg') or [''])[0]
            else:
                target=href
            target=unquote(target).strip()
            if not re.match(r'^https?://',target,re.I): continue
            if target in seen: continue
            seen.add(target)
            container=a.find_parent(class_='result') or a.parent
            snippet=container.select_one('.result__snippet') if container else None
            out.append({"title":a.get_text(" ",strip=True)[:300],"url":target,
                        "snippet":snippet.get_text(" ",strip=True)[:500] if snippet else ""})
            if len(out)>=max_results: break
        return out

    def search(self, query, max_results=6):
        if not query or len(query)>500: raise ValueError("Invalid search query")
        headers={"User-Agent":"Mozilla/5.0 Alice/0.11"}
        r=requests.get("https://www.google.com/search",params={"q":query},headers=headers,timeout=self.timeout)
        r.raise_for_status()
        out=self._google_results(r.text,max_results)
        if not out:
            # Google may return a JavaScript retry/consent page with HTTP 200.
            # Fall back to its lightweight HTML search page rather than
            # misreporting that ALICE found no sources.
            fallback=requests.get("https://html.duckduckgo.com/html/",params={"q":query},headers=headers,timeout=self.timeout)
            fallback.raise_for_status()
            out=self._duckduckgo_results(fallback.text,max_results)
        return {"ok":True,"query":query,"results":out}

    def fetch_text(self,url,max_chars=12000):
        html,final_url=self._get_public_page(url)
        soup=BeautifulSoup(html,'html.parser')
        published_at = None
        for selector in (
            'meta[property="article:published_time"]',
            'meta[property="og:published_time"]',
            'meta[name="datePublished"]',
            'meta[itemprop="datePublished"]',
            'meta[name="pubdate"]',
            'meta[name="date"]',
            'time[datetime]',
        ):
            node=soup.select_one(selector)
            candidate=(node.get("content") or node.get("datetime") or "").strip() if node else ""
            if candidate and len(candidate) <= 100:
                published_at=candidate
                break
        for x in soup(['script','style','noscript']): x.decompose()
        # Prefer the page's article/main body over navigation and footer text.
        # This makes relevant facts survive the short evidence budget used by
        # ALICE's local synthesizer, especially on long institutional pages.
        content=soup.find('article') or soup.find('main') or soup.body or soup
        for x in content(['nav','header','footer','aside']): x.decompose()
        retrieved_epoch=time.time()
        return {
            "ok":True,"url":final_url,
            "title":soup.title.get_text(' ',strip=True) if soup.title else '',
            "text":content.get_text(' ',strip=True)[:max_chars],
            "published_at":published_at,
            "retrieved_at":datetime.fromtimestamp(retrieved_epoch,timezone.utc).isoformat(timespec="seconds"),
            "retrieved_at_epoch":retrieved_epoch,
        }
