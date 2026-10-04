import ipaddress
import json
import re
import socket
from urllib.parse import urlparse, parse_qs, parse_qsl, urlencode, urlunparse
import httpx
from bs4 import BeautifulSoup

def canonicalize_url(url: str) -> str:
    """Normalize recipe URLs to prevent duplicate imports (e.g. tracking params & YouTube variants)."""
    if not url:
        return ""
    url = str(url).strip()
    p = urlparse(url)
    if not p.netloc and not p.path:
        return url
    scheme = p.scheme.lower() or "https"
    netloc = p.netloc.lower().split(":", 1)[0]
    
    # YouTube canonicalization (watch?v=..., youtu.be/..., shorts/...)
    yt_hosts = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")
    if netloc in yt_hosts:
        video_id = None
        if netloc == "youtu.be":
            video_id = p.path.lstrip("/").split("/")[0].split("?")[0]
        elif "/shorts/" in p.path:
            video_id = p.path.split("/shorts/")[1].split("/")[0].split("?")[0]
        else:
            qs = parse_qs(p.query)
            video_id = qs.get("v", [None])[0]
        if video_id:
            video_id = re.sub(r"[^a-zA-Z0-9_-]", "", video_id)
            return f"https://www.youtube.com/watch?v={video_id}"

    # General URL cleanup: strip trailing slash and tracking query params
    path = p.path.rstrip("/") or "/"
    query_tuples = parse_qsl(p.query, keep_blank_values=False)
    filtered_queries = [
        (k, v) for k, v in query_tuples
        if not (k.lower().startswith("utm_") or k.lower() in ("ref", "si", "fbclid", "gclid", "igshid", "feature", "pp"))
    ]
    query = urlencode(filtered_queries)
    return urlunparse((scheme, netloc, path, "", query, ""))


HEADERS = {"User-Agent":"Mozilla/5.0 RecipeBox/1.0"}
MEDIA_SOURCES = {
    "youtube.com": ("YouTube", "🎬"),
    "youtu.be": ("YouTube", "🎬"),
    "instagram.com": ("Instagram", "📸"),
    "facebook.com": ("Facebook", "📘"),
    "fb.watch": ("Facebook", "📘"),
}

def media_source(url):
    host=urlparse(url).netloc.lower().split(":", 1)[0]
    return next((details for domain, details in MEDIA_SOURCES.items()
                 if host == domain or host.endswith("."+domain)), None)

def minutes(value):
    if not value: return None
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", str(value))
    if m: return int(m.group(1) or 0)*1440 + int(m.group(2) or 0)*60 + int(m.group(3) or 0)
    nums = re.findall(r"\d+", str(value)); return int(nums[0]) if nums else None

def find_recipe(value):
    if isinstance(value, list):
        for item in value:
            found = find_recipe(item)
            if found: return found
    if isinstance(value, dict):
        typ = value.get("@type", "")
        if typ == "Recipe" or (isinstance(typ, list) and "Recipe" in typ): return value
        for key in ("@graph", "mainEntity"):
            found = find_recipe(value.get(key))
            if found: return found
    return None

def text_steps(value):
    """Extract step texts from recipeInstructions (list, HowToStep or HowToSection)."""
    if value is None: return []
    if isinstance(value, str):
        return [BeautifulSoup(step, "html.parser").get_text(" ", strip=True) for step in value.splitlines() if step.strip()]
    if isinstance(value, dict):
        if value.get("text"): return [value["text"]]
        if "itemListElement" in value: return text_steps(value["itemListElement"])
        return []
    out=[]
    for item in value:
        if isinstance(item, str): out.append(item)
        elif isinstance(item, dict):
            if item.get("text"): out.append(item["text"])
            elif item.get("itemListElement"): out.extend(text_steps(item["itemListElement"]))
    return out

def _public_addresses(url):
    """Resolve a URL's host once and return (parsed URL, port, validated public addresses).

    Blocks loopback, private/LAN, link-local (e.g. cloud metadata), CGNAT,
    unspecified, reserved and multicast addresses, also when reached through
    hostnames such as 'localhost' or rebinding DNS services: every resolved
    address must be public.
    """
    parsed = urlparse(str(url))
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Nur http(s)-Links dürfen importiert werden.")
    host = parsed.hostname
    if not host:
        raise ValueError("Ungültiger Link.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Nur Standard-Web-Ports (80/443) dürfen abgerufen werden.")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Hostname konnte nicht aufgelöst werden.") from None
    addresses = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            raise ValueError("Interne Adressen dürfen nicht abgerufen werden.")
        if ip not in addresses:
            addresses.append(ip)
    if not addresses:
        raise ValueError("Hostname konnte nicht aufgelöst werden.")
    return parsed, port, addresses


def validate_public_url(url):
    """Kept for callers that only need the yes/no check."""
    _public_addresses(url)
    return True


def fetch_public(url, timeout=25, max_redirects=5):
    """GET a public URL without a second, independent DNS lookup.

    The connection goes to an address that was validated above (the hostname is
    never handed to the HTTP transport for resolution), while the Host header and
    TLS SNI/certificate verification still use the original hostname. Redirects
    are followed manually so every hop gets the same check.
    """
    for _ in range(max_redirects + 1):
        parsed, port, addresses = _public_addresses(url)
        ip = addresses[0]
        literal = f"[{ip}]" if ip.version == 6 else str(ip)
        netloc = literal if parsed.port is None else f"{literal}:{parsed.port}"
        pinned = urlunparse(parsed._replace(netloc=netloc))
        host_header = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            request = client.build_request("GET", pinned, headers={**HEADERS, "Host": host_header},
                                           extensions={"sni_hostname": parsed.hostname})
            response = client.send(request)
            response.read()
        if response.is_redirect and response.headers.get("location"):
            from urllib.parse import urljoin
            url = urljoin(url, response.headers["location"])
            continue
        response.raise_for_status()
        return response
    raise ValueError("Zu viele Weiterleitungen.")


def extract(url):
    clean_url = canonicalize_url(url) or url
    source = media_source(clean_url)
    if source:
        res = extract_media(clean_url, *source)
        res["source_url"] = clean_url
        return res
    response = fetch_public(clean_url, timeout=25)
    soup = BeautifulSoup(response.text, "html.parser")
    node = None
    for script in soup.select('script[type="application/ld+json"]'):
        try: node = find_recipe(json.loads(script.string or ""))
        except (json.JSONDecodeError, TypeError): continue
        if node: break
    if not node:
        for junk in soup.select("script, style, nav, footer, header"):
            junk.decompose()
        article = soup.select_one("article, main") or soup
        raw = article.get_text("\n", strip=True)[:30000]
        ingredients, instructions = split_recipe_text(raw)
        if not raw:
            raise ValueError("No recipe text found")
        title = soup.select_one("h1, title")
        return {"title": title.get_text(" ", strip=True) if title else "Recipe", "emoji": "🍽️", "source_url": clean_url,
                "source_type": "Webseite", "ingredients": ingredients, "instructions": instructions,
                "raw_text": raw, "tags": [], "servings": ""}
    image = node.get("image", "")
    if isinstance(image, list): image = image[0] if image else ""
    if isinstance(image, dict): image = image.get("url", "")
    nutrition = node.get("nutrition") or {}; kcal = re.findall(r"\d+", str(nutrition.get("calories", "")))
    duration = minutes(node.get("totalTime")) or (minutes(node.get("prepTime")) or 0)+(minutes(node.get("cookTime")) or 0) or None
    return {"title": node.get("name", "Unbenanntes Rezept"), "emoji": "🍽️", "image_url": image, "source_url": clean_url,
      "source_type": "Webseite", "ingredients": node.get("recipeIngredient") or [], "instructions": text_steps(node.get("recipeInstructions")),
      "tags": [x.strip() for x in str(node.get("keywords", "")).split(",") if x.strip()], "duration_minutes": duration,
      "servings": str(node.get("recipeYield", "")), "calories": int(kcal[0]) if kcal else None}
def split_recipe_text(text):
    """Separate labelled sections without inventing quantities or preparation."""
    ingredients, instructions = [], []
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        heading = re.sub(r"^[#*\s]+|[:：*\s]+$", "", line).casefold()
        if re.fullmatch(r"(?:ingredients?|zutaten|ingrédients|ingredientes|ingredienti|ingredienser|材料|原料|सामग्री)(?:\s*\([^)]*\))?", heading):
            section = ingredients; continue
        if re.fullmatch(r"(?:instructions?|directions?|method|preparation|steps?|zubereitung|anleitung|préparation|preparación|preparazione|modo de preparo|tillagning|fremgangsmåde|fremgangsmate|fremgangsmåte|作り方|做法|विधि)", heading):
            section = instructions; continue
        if re.match(r"(?:nutrition|notes?|subscribe|follow|nährwerte|anmerkungen)\b", heading):
            section = None; continue
        if section is not None:
            section.append(re.sub(r"^[•*\-]\s+", "", line))
        elif re.match(r"^(?:[•*\-]\s*)?\d+(?:[.,/]\d+)?\s*(?:g|kg|ml|l|cups?|tbsp|tsp|el|tl|gram\w*)\b", line, re.I):
            ingredients.append(re.sub(r"^[•*\-]\s+", "", line))
    return ingredients, instructions


def clean_media_text(text: str) -> str:
    """Strip promotional links, social media handles, and separator lines from video descriptions."""
    if not text:
        return ""
    cleaned = []
    prev_blank = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if not prev_blank:
                cleaned.append("")
                prev_blank = True
            continue
        if re.match(r"^(?:[-—_=*~#]{3,})$", s):
            continue
        if re.match(r"^(?:[►▶➤👉•\-\*]\s*)?https?://\S+$", s, re.IGNORECASE):
            continue
        if any(marker in s.lower() for marker in [
            "amzn.to", "bit.ly", "instagram.com", "tiktok.com", "facebook.com",
            "twitter.com", "youtube.com/playlist", "/newsletter"
        ]):
            continue
        cleaned.append(line)
        prev_blank = False
    result = "\n".join(cleaned).strip()
    return result or text


def extract_youtube_fallback(url):
    import urllib.request, json, re
    title = ''
    thumbnail = ''
    try:
        oembed_url = f'https://www.youtube.com/oembed?url={url}&format=json'
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            oed = json.loads(resp.read().decode('utf-8'))
            title = oed.get('title', '')
            thumbnail = oed.get('thumbnail_url', '')
    except Exception:
        pass

    description = ''
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            page_html = resp.read().decode('utf-8', errors='ignore')

        m = re.search(r'var ytInitialData = ({.*?});</script>', page_html)
        if m:
            data = json.loads(m.group(1))
            for ep in data.get('engagementPanels', []):
                content = ep.get('engagementPanelSectionListRenderer', {}).get('content', {})
                items = content.get('structuredDescriptionContentRenderer', {}).get('items', [])
                for item in items:
                    desc_body = item.get('expandableVideoDescriptionBodyRenderer', {})
                    desc_text = desc_body.get('attributedDescriptionBodyText', {}).get('content')
                    if desc_text:
                        description = desc_text
                        break
                if description:
                    break
    except Exception:
        pass

    return {
        'title': title or 'YouTube-Rezept',
        'description': description,
        'thumbnail': thumbnail,
        'duration': None,
        'tags': []
    }


def _caption_track(info):
    """Pick the spoken-language captions: uploaded subtitles first, then YouTube's original-language auto captions."""
    spoken = (info.get("language") or "").split("-")[0].lower()
    for tracks, original_suffix in ((info.get("subtitles") or {}, None), (info.get("automatic_captions") or {}, "-orig")):
        keys = [key for key in tracks if key != "live_chat" and tracks[key]]
        preferred = ([key for key in keys if original_suffix and key.endswith(original_suffix)]
                     + [key for key in keys if spoken and key.split("-")[0].lower() == spoken])
        if original_suffix is None and not preferred:
            preferred = keys[:1]
        for key in preferred:
            formats = {row.get("ext"): row.get("url") for row in tracks[key] if row.get("url")}
            for ext in ("json3", "vtt"):
                if formats.get(ext):
                    return ext, formats[ext]
    return None


def media_transcript(info, limit=16000):
    """Return the video's spoken text; descriptions often omit the actual recipe."""
    track = _caption_track(info)
    if not track:
        return ""
    ext, caption_url = track
    try:
        response = fetch_public(caption_url, timeout=15)
        if ext == "json3":
            lines = ["".join(segment.get("utf8", "") for segment in event.get("segs") or [])
                     for event in response.json().get("events", [])]
        else:
            lines = [line for line in response.text.splitlines()
                     if line.strip() and "-->" not in line and not line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))]
            lines = [re.sub(r"<[^>]+>", "", line) for line in lines]
    except (httpx.HTTPError, ValueError):
        return ""
    words, previous = [], None
    for line in lines:
        line = re.sub(r"\[[^\]]{1,30}\]", " ", line).strip()
        if line and line != previous:
            words.append(line)
        previous = line or previous
    return re.sub(r"\s+", " ", " ".join(words)).strip()[:limit]


def extract_media(url, source_type, emoji):
    """Extract title/description metadata from a supported video URL.
    Only public, login-free posts can be read; the AI pipeline structures the text afterwards.
    """
    info = None
    import yt_dlp
    opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": False,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        if "youtube.com" in url or "youtu.be" in url:
            try:
                info = extract_youtube_fallback(url)
            except Exception:
                pass
        if not info or not info.get("title"):
            raise ValueError(
                f"{source_type}-Beitrag konnte nicht gelesen werden. Er muss öffentlich und ohne Anmeldung erreichbar sein."
            ) from exc

    # Split video into 14‑minute chunks if needed (guard removed)
    duration_sec = info.get("duration")
    # Calculate number of 14‑minute chunks (840 s each)
    chunks = 1
    if duration_sec and duration_sec > 840:
        import math
        chunks = math.ceil(duration_sec / 840)
    # NOTE: The actual chunk processing (e.g., transcript extraction) is handled later by the AI pipeline.

    raw = "\n".join(filter(None, [info.get("title"), info.get("description")]))
    text = clean_media_text(raw)
    return {
        "transcript": media_transcript(info),
        "title": info.get("title") or f"{source_type}-Rezept",
        "emoji": emoji,
        "image_url": info.get("thumbnail", ""),
        "source_url": url,
        "source_type": source_type,
        "ingredients": [],
        "instructions": [],
        "tags": info.get("tags") or [],
        "duration_minutes": None,
        "servings": "",
        "calories": None,
        "raw_text": text,
        "chunks": chunks,
    }


def extract_youtube(url):
    return extract_media(url, "YouTube", "🎬")

def duration_class(n):
    if n is None:return "unbekannt"
    return "kurz" if n <= 30 else "mittel" if n <= 90 else "lang"
