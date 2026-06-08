import os
import requests
from flask import Flask, request, abort
from openai import OpenAI

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route("/", methods=['GET'])
def index():
    return "LINE Bot Pure-HTTP Service is running!"

@app.route("/api/webhook", methods=['POST'])
def callback():
    body = request.get_json()
    
    if not body or 'events' not in body or len(body['events']) == 0:
        return 'OK'

    for event in body['events']:
        if event.get('type') == 'message' and event['message'].get('type') == 'text':
            reply_token = event['replyToken']
            raw_message = event['message']['text'].strip() # 去除前後空白
            
            # --- 🤖 關鍵過濾機制 (支援 Tag 標記) ---
            # 把所有可能的 Tag 寫法放進來 (注意後面都有加逗號，這才是正確的 Python Tuple 格式)
            # 這裡不分大小寫，包含你手打的完整名稱，或是 LINE 內建 Tag 產生的名稱
            trigger_words = ("@Ai","@AI","@ai","@腫忠AI機器人","@腫忠ai機器人", "@腫忠", "@腫忠AI", "@腫忠ai")
            
            # 檢查訊息開頭是不是這些標記字串
            has_trigger = any(raw_message.lower().startswith(word) for word in trigger_words)
            
            # 如果沒有被標記，直接忽略這筆訊息
            if not has_trigger:
                continue
                
            # 如果是被點名，把開頭的標記切掉，只留下真正的問題
            user_message = raw_message
            for word in trigger_words:
                if raw_message.lower().startswith(word):
                    # 切掉標記，並再次用 .strip() 把標記後面的空白字元也吃掉
                    user_message = raw_message[len(word):].strip()
                    break
            
            # 如果切完發現大家只 Tag 它卻沒說話
            if not user_message:
                user_message = "嗨！點名我做什麼呢？有什麼我可以幫忙的？"
            # ------------------------------------

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

            # 2. 回傳給 LINE
            line_url = "https://api.line.me/v2/bot/message/reply"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
            }
            payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": reply_text}]
            }
            
            try:
                requests.post(line_url, json=payload, headers=headers)
            except Exception:
                pass

    return 'OK'

if __name__ == "__main__":
    app.run()