import socket
import ssl
import tkinter
import sys
import tkinter.font

WIDTH, HEIGHT = 800, 600
SCROLL_STEP = 100
HSTEP, VSTEP = 13, 18
FONTS = {}

# --- URL fetcher ---
class URL:
    def __init__(self, url):
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

        if "/" not in url:
            url += "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

    def request(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = 80 if self.scheme == "http" else 443

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = f"GET {self.path} HTTP/1.0\r\nHost: {self.host}\r\n\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content = response.read()
        s.close()
        return content

# --- Tokens ---
class Text:
    def __init__(self, text, parent=None):
        self.text = text
        self.children = []
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent=None):
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent

    def __repr__(self):
        return "<" + self.tag + ">"

# --- Fonts ---
def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        FONTS[key] = font
    return FONTS[key]

# --- Layout engine ---
class Layout:
    def __init__(self, tree):
        self.display_list = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.line = []
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.needs_space = False
        self.is_centered = False
        self.recurse(tree)
        self.flush()

    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size = max(4, self.size - 2)
        elif tag == "big":
            self.size += 4
        elif tag == "center":
            self.is_centered = True

    def close_tag(self, tag):
        if tag == "i":
            self.style = "roman"
        elif tag == "b":
            self.weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag == "big":
            self.size = max(4, self.size - 4)
        elif tag == "center":
            self.is_centered = False

    def recurse(self, tree):
        self.token(tree)
        if isinstance(tree, Element):
            for child in tree.children:
                self.recurse(child)

    def word(self, word):
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word)
        space = font.measure(" ")

        if self.cursor_x + w >= WIDTH - HSTEP:
            self.flush()

        self.line.append((self.cursor_x, word, font))
        self.cursor_x += w + space
        self.needs_space = True

    def token(self, tok):
        if isinstance(tok, Text):
            for word in tok.text.split():
                self.word(word)
        elif isinstance(tok, Element):
            tag = tok.tag
            if tag == "br":
                self.flush()
            elif tag == "p":
                self.flush()
                self.cursor_y += VSTEP
            elif tag == "/p":
                self.flush()
                self.cursor_y += VSTEP
            else:
                if not tag.startswith("/"):
                    self.open_tag(tag)
                else:
                    self.close_tag(tag[1:])

    def flush(self):
        if not self.line:
            return
        ascents = [font.metrics("ascent") for _, _, font in self.line]
        descents = [font.metrics("descent") for _, _, font in self.line]
        max_ascent = max(ascents)
        max_descent = max(descents)
        baseline = self.cursor_y + int(1.25 * max_ascent)

        for x, word, font in self.line:
            ascent = font.metrics("ascent")
            y = baseline - ascent
            self.display_list.append((x, y, word, font))

        self.cursor_y = baseline + int(1.25 * max_descent)
        self.cursor_x = HSTEP
        self.line = []

# --- Browser GUI ---
class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.title("Monkey Browser \U0001F412")
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<MouseWheel>", self.on_mouse_scroll)
        self.window.bind("<Button-4>", self.on_mouse_scroll)
        self.window.bind("<Button-5>", self.on_mouse_scroll)

    def on_mouse_scroll(self, event):
        if hasattr(event, "delta") and event.delta > 0 or getattr(event, "num", 0) == 4:
            self.scroll = max(0, self.scroll - SCROLL_STEP)
        elif hasattr(event, "delta") and event.delta < 0 or getattr(event, "num", 0) == 5:
            self.scroll += SCROLL_STEP
        self.draw()

    def scrolldown(self, e=None):
        self.scroll += SCROLL_STEP
        self.draw()

    def scrollup(self, e=None):
        self.scroll = max(0, self.scroll - SCROLL_STEP)
        self.draw()

    def load(self, url):
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        self.display_list = Layout(self.nodes).display_list
        self.draw()

    def run(self):
        self.window.mainloop()

    def draw(self):
        self.canvas.delete("all")
        for x, y, word, font in self.display_list:
            if y > self.scroll + HEIGHT:
                continue
            if y + VSTEP < self.scroll:
                continue
            self.canvas.create_text(x, y - self.scroll, text=word, font=font, anchor="nw")

# --- HTML Parser ---
class HTMLParser:
    SELF_CLOSING_TAGS = [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    ]
    HEAD_TAGS = [
        "base", "basefont", "bgsound", "noscript",
        "link", "meta", "title", "style", "script",
    ]

    def __init__(self, body):
        self.body = body
        self.unfinished = []

    def get_attributes(self, text):
        parts = text.split()
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", '"']:
                    value = value[1:-1]
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def parse(self):
        text = ""
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text:
                    self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()

    def add_text(self, text):
        if text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"): return
        self.implicit_tags(tag)
        if tag.startswith("/"):
            if len(self.unfinished) == 1: return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, {}, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

# --- Entry Point ---
if __name__ == "__main__":
    browser = Browser()
    browser.load(URL(sys.argv[1]))
    browser.run()
