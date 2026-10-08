"""Static HTML asset resolution at the URLs a browser actually loads."""
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

from content import PreviewError

ASSET_ATTRS = {
    "script": ("src",), "img": ("src",), "source": ("src",),
    "audio": ("src",), "video": ("src", "poster"), "iframe": ("src",),
    "embed": ("src",), "object": ("data",), "input": ("src",),
    "image": ("href", "xlink:href"), "use": ("href", "xlink:href"),
}
LINK_ASSETS = {"stylesheet", "icon", "preload", "modulepreload", "manifest", "apple-touch-icon"}


class Assets(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.base = None
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "base" and "href" in attrs and self.base is None:
            self.base = attrs["href"]
        keys = ASSET_ATTRS.get(tag, ())
        if tag == "link" and set((attrs.get("rel") or "").lower().split()) & LINK_ASSETS:
            keys = ("href",)
        for key in keys:
            if attrs.get(key):
                # Preserve parser order: an asset before <base> starts loading
                # against the document URL, not a later declared base.
                self.urls.append((self.base, attrs[key]))
        if tag in ("img", "source") and attrs.get("srcset"):
            # Conservative supported srcset: explicit ordinary URL candidates.
            # Data URLs containing commas fail closed rather than guessed parsing.
            for candidate in attrs["srcset"].split(","):
                words = candidate.strip().split()
                if not words:
                    raise PreviewError("Readiness cannot resolve this srcset; export explicit public asset URLs.")
                self.urls.append((self.base, words[0]))

    handle_startendtag = handle_starttag


def resolved_assets(html, document_url, prefix, selected):
    try:
        parser = Assets()
        parser.feed(html.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise PreviewError("Readiness requires UTF-8 HTML with resolvable public asset URLs.") from error
    origin = urlsplit(document_url)
    result = []
    for base, reference in parser.urls:
        if reference.startswith("#") or reference.startswith("data:"):
            continue  # inline bytes/fragments do not fetch another network asset
        asset_url = urlsplit(urljoin(urljoin(document_url, base) if base is not None else document_url,
                                     reference))
        path = unquote(asset_url.path, errors="strict")
        if (asset_url.scheme, asset_url.netloc) != (origin.scheme, origin.netloc) or not path.startswith(prefix + "/"):
            raise PreviewError("HTML asset escapes this preview URL. Export assets under " + prefix +
                               "/ (not /assets/ or another host), then restart and verify.")
        name = path[len(prefix) + 1:]
        if name not in selected:
            raise PreviewError("HTML asset does not resolve to a selected public file. Put <base href=\"" +
                               prefix + "/\"> before relative assets, or export with that base; "
                               "select every asset with --file, restart and verify.")
        result.append((asset_url.path + ("?" + asset_url.query if asset_url.query else ""), selected[name]))
    return result


def absent_asset(selected):
    index = 0
    while True:
        name = "preview-denial-probe-" + str(index) + ".js"
        if name not in selected:
            return "/" + name
        index += 1


def other_slug(slug):
    return "preview-isolation-probe" if slug != "preview-isolation-probe" else "preview-isolation-probe-1"
