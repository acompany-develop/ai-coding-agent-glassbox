"""ANSIカラーユーティリティ

ターミナル出力を色付けするためのシンプルなユーティリティ。
追加の依存関係なしで動作。
"""


class Colors:
    """ANSIエスケープコード"""
    # リセット
    RESET = "\033[0m"

    # 通常色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # 明るい色
    BRIGHT_BLACK = "\033[90m"  # グレー
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # スタイル
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"


def colorize(text: str, color: str) -> str:
    """テキストに色を付ける"""
    return f"{color}{text}{Colors.RESET}"


# ショートカット関数
def red(text: str) -> str:
    return colorize(text, Colors.RED)

def green(text: str) -> str:
    return colorize(text, Colors.GREEN)

def yellow(text: str) -> str:
    return colorize(text, Colors.YELLOW)

def blue(text: str) -> str:
    return colorize(text, Colors.BLUE)

def magenta(text: str) -> str:
    return colorize(text, Colors.MAGENTA)

def cyan(text: str) -> str:
    return colorize(text, Colors.CYAN)

def gray(text: str) -> str:
    return colorize(text, Colors.BRIGHT_BLACK)

def bold(text: str) -> str:
    return colorize(text, Colors.BOLD)

def dim(text: str) -> str:
    return colorize(text, Colors.DIM)


# タグ付きprint用
def print_init(msg: str) -> None:
    """[INIT] 緑色"""
    print(f"{Colors.GREEN}[INIT]{Colors.RESET} {msg}")

def print_agent(msg: str) -> None:
    """[AGENT] シアン"""
    print(f"{Colors.CYAN}[AGENT]{Colors.RESET} {msg}")

def print_think(msg: str) -> None:
    """[THINK] 黄色"""
    print(f"{Colors.YELLOW}[THINK]{Colors.RESET} {msg}")

def print_act(msg: str) -> None:
    """[ACT] マゼンタ"""
    print(f"{Colors.MAGENTA}[ACT]{Colors.RESET} {msg}")

def print_observe(msg: str) -> None:
    """[OBSERVE] 青"""
    print(f"{Colors.BLUE}[OBSERVE]{Colors.RESET} {msg}")

def print_llm(msg: str) -> None:
    """[LLM] グレー"""
    print(f"{Colors.BRIGHT_BLACK}[LLM]{Colors.RESET} {msg}")

def print_error(msg: str) -> None:
    """[ERROR] 赤"""
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")

def print_history(msg: str) -> None:
    """[HISTORY] グレー"""
    print(f"{Colors.BRIGHT_BLACK}[HISTORY]{Colors.RESET} {msg}")

def print_separator(char: str = "─", width: int = 60) -> None:
    """区切り線（グレー）"""
    print(gray(char * width))

def print_header(title: str, char: str = "=", width: int = 60) -> None:
    """ヘッダー（太字）"""
    print(bold(char * width))
    print(bold(title))
    print(bold(char * width))
