import requests


def telegram_bot_send_text(token: str, chat_id: str, message: str) -> dict:
    send_text = (
        "https://api.telegram.org/bot"
        + token
        + "/sendMessage?chat_id="
        + chat_id
        + "&parse_mode=Markdown&text="
        + message
    )
    response = requests.get(send_text, timeout=10)
    return response.json()
