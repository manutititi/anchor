# core/utils/colors.py

def color(text, code): return f"\033[{code}m{text}\033[0m"

def red(text): return color(text, "0;31")
def green(text): return color(text, "0;32")
def yellow(text): return color(text, "0;33")
def blue(text): return color(text, "1;34")
def cyan(text): return color(text, "1;36")
def magenta(text): return color(text, "0;35")
def gray(text): return color(text, "0;37")
def bold(text): return color(text, "1")
def dim(text): return color(text, "2")
def vivid_green(text): return color(text, "1;92")
def reset(): return "\033[0m"

# Modo por clase si querés también usarlo como atributo
class Colors:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[1;34m"
    CYAN = "\033[1;36m"
    GRAY = "\033[0;37m"
    MAGENTA = "\033[0;35m"

    @classmethod
    def colorize(cls, text, color):
        return f"{getattr(cls, color.upper(), cls.RESET)}{text}{cls.RESET}"
