import os
import requests
from flask import Flask, request, abort
from openai import OpenAI

app = Flask(__name__)

# 從 Vercel 後台抓取環境變數
LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route("/", methods=['GET'])
def index():
    return "LINE Bot Pure-HTTP Service is running!"

@app.route("/api/webhook", methods=['POST'])
def callback():
    body = request.get_json()
    
    # 預防 LINE 後台 Verify 時傳送的空事件
    if not body or 'events' not in body or len(body['events']) == 0:
        return 'OK'

    for event in body['events']:
        # 確保是文字訊息事件
        if event.get('type') == 'message' and event['message'].get('type') == 'text':
            reply_token = event['replyToken']
            user_message = event['message']['text']
            
            # 1. 呼叫 OpenAI 產生回覆
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "你是一個幽默、溫暖且非常有幫助的 LINE 智慧助理。"},
                        {"role": "user", "content": user_message}
                    ]
                )
                reply_text = response.choices[0].message.content
            except Exception as e:
                reply_text = f"糟糕，AI大腦打結了... (錯誤訊息: {str(e)})"

            # 2. 用純 HTTP POST 把訊息回傳給 LINE 伺服器
            line_url = "https://api.line.me/v2/bot/message/reply"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
            }
            payload = {
                "replyToken": reply_token,
                "messages": [
                    {
                        "type": "text",
                        "text": reply_text
                    }
                ]
            }
            
            try:
                requests.post(line_url, json=payload, headers=headers)
            except Exception:
                pass

    return 'OK'

if __name__ == "__main__":
    app.run()