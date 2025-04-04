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
    def __init__(self, text):
        self.text = text

class Tag:
    def __init__(self, tag):
        self.tag = tag.lower()

# --- Lex HTML to tokens ---
def lex(body):
    out = []
    buffer = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
            if buffer:
                words = buffer.split()
                for word in words:
                    out.append(Text(word))
            buffer = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(buffer.strip()))
            buffer = ""
        else:
            buffer += c
    if not in_tag and buffer:
        words = buffer.split()
        for word in words:
            out.append(Text(word))
    return out

# --- Fonts ---
def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight,
            slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

# --- Layout engine ---
class Layout:
    def __init__(self, tokens):
        self.display_list = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.line = []
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.needs_space = False  # Track if a space is needed
        self.is_centered = False  # Track centered text
        for tok in tokens:
            self.token(tok)
        self.flush()

    def token(self, tok):
        if isinstance(tok, Text):
            font = get_font(self.size, self.weight, self.style)
            w = font.measure(tok.text)
            space = font.measure(" ")
            if self.cursor_x + w >= WIDTH - HSTEP:
                self.flush()
            self.line.append((self.cursor_x, tok.text, font))
            self.cursor_x += w + space
        elif isinstance(tok, Tag):
            tag = tok.tag
            if tag == "br":
                self.flush()
            elif tag == "p":
                self.flush()
                self.cursor_y += VSTEP  # Add extra spacing for paragraphs
            elif tag == "/p":
                self.flush()
                self.cursor_y += VSTEP
            elif tag == "b":
                self.weight = "bold"
            elif tag == "/b":
                self.weight = "normal"
            elif tag == "i":
                self.style = "italic"
            elif tag == "/i":
                self.style = "roman"
            elif tag == "small":
                self.size = max(4, self.size - 2)
            elif tag == "/small":
                self.size += 2
            elif tag == "big":
                self.size += 4
            elif tag == "/big":
                self.size = max(4, self.size - 4)


    def word(self, word):
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word)
        space = font.measure(" ") if self.needs_space else 0

        if self.cursor_x + space + w >= WIDTH - HSTEP:
            self.flush()
            space = 0  # Reset space at new line

        if self.is_centered:
            x_pos = (WIDTH - w) // 2  # Centered text
        else:
            x_pos = self.cursor_x + space

        self.line.append((x_pos, word, font))
        self.cursor_x = x_pos + w
        self.needs_space = True  # Next word will need space

    def flush(self):
        if not self.line:
            return
        # Find the max ascent and descent among words in the line
        metrics = [font.metrics() for _, _, font in self.line]
        max_ascent = max(metric["ascent"] for metric in metrics)
        max_descent = max(metric["descent"] for metric in metrics)
        baseline = self.cursor_y + 1.25 * max_ascent

        for x, word, font in self.line:
            ascent = font.metrics()["ascent"]
            y_offset = baseline - ascent  # Align word to the baseline
            self.display_list.append((x, y_offset, word, font))

        self.cursor_y = baseline + 1.25 * max_descent
        self.cursor_x = HSTEP
        self.line = []


# --- Browser GUI ---
class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.title("Monkey Browser 🐒")
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
        tokens = lex(body)
        self.display_list = Layout(tokens).display_list
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

# --- Main execution ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python browser.py <url>")
        sys.exit(1)

    browser = Browser()
    browser.load(URL(sys.argv[1]))
    browser.run()
