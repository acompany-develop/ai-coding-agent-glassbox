import requests
from bs4 import BeautifulSoup

from .base import Tool


class WebFetchTool(Tool):
    """URLからコンテンツを取得するツール

    指定されたURLのコンテンツを取得し、HTMLの場合はテキストに変換する。
    Claude CodeのWebFetchツールに相当。

    学びのポイント:
    - エージェントの情報源を外部に拡張
    - HTML→テキスト変換の必要性
    - タイムアウトとエラーハンドリング
    """

    DEFAULT_TIMEOUT = 30  # seconds
    DEFAULT_MAX_LENGTH = 50000  # characters

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch content from a URL. "
            "HTML pages are converted to readable text. "
            "Use this to retrieve documentation, API references, or other web content."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (default: {self.DEFAULT_TIMEOUT})",
                    "default": self.DEFAULT_TIMEOUT,
                },
            },
            "required": ["url"],
        }

    def execute(self, url: str, timeout: int | None = None, **kwargs) -> str:
        """URLからコンテンツを取得する

        Args:
            url: 取得するURL
            timeout: タイムアウト秒数

        Returns:
            取得したコンテンツ、またはエラーメッセージ
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            # HTTPリクエストを送信
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI-Coding-Agent/1.0; "
                    "+https://github.com/example/ai-coding-agent)"
                ),
            }

            response = requests.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()

            # Content-Typeを確認
            content_type = response.headers.get("Content-Type", "").lower()

            if "text/html" in content_type:
                # HTMLをテキストに変換
                text = self._html_to_text(response.text)
            elif "application/json" in content_type:
                # JSONはそのまま
                text = response.text
            elif "text/" in content_type:
                # その他のテキスト形式
                text = response.text
            else:
                return f"Error: Unsupported content type: {content_type}"

            # 長さを制限
            if len(text) > self.DEFAULT_MAX_LENGTH:
                text = text[: self.DEFAULT_MAX_LENGTH]
                text += f"\n\n[Content truncated at {self.DEFAULT_MAX_LENGTH} characters]"

            return text

        except requests.exceptions.Timeout:
            return f"Error: Request timed out after {timeout} seconds"
        except requests.exceptions.ConnectionError:
            return f"Error: Could not connect to {url}"
        except requests.exceptions.HTTPError as e:
            return f"Error: HTTP error {e.response.status_code}: {e.response.reason}"
        except requests.exceptions.RequestException as e:
            return f"Error: Request failed: {e}"
        except Exception as e:
            return f"Error fetching URL: {e}"

    def _html_to_text(self, html: str) -> str:
        """HTMLをプレーンテキストに変換する"""
        soup = BeautifulSoup(html, "html.parser")

        # 不要な要素を削除
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        # テキストを抽出
        text = soup.get_text(separator="\n", strip=True)

        # 連続する空行を1つにまとめる
        lines = text.split("\n")
        cleaned_lines = []
        prev_empty = False

        for line in lines:
            line = line.strip()
            if not line:
                if not prev_empty:
                    cleaned_lines.append("")
                    prev_empty = True
            else:
                cleaned_lines.append(line)
                prev_empty = False

        return "\n".join(cleaned_lines)
