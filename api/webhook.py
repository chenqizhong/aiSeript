import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI

app = Flask(__name__)

# 從 Vercel 後台抓取環境變數
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route("/", methods=['GET'])
def index():
    return "LINE Bot Service is running!"

@app.route("/api/webhook", methods=['POST'])
def callback():
    # 獲取 LINE 傳來的簽章驗證
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 當收到文字訊息時的處理邏輯
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    
    try:
        # 呼叫 OpenAI 產生回覆
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 使用高 CP 值的輕量模型
            messages=[
                {"role": "system", "content": "你是一個幽默、溫暖且非常有幫助的 LINE 智慧助理。"},
                {"role": "user", "content": user_message}
            ]
        )
        reply_text = response.choices[0].message.content
    except Exception as e:
        reply_text = f"糟糕，我的大腦好像開小差了... (錯誤訊息: {str(e)})"

    # 將 AI 的回覆傳回給使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()