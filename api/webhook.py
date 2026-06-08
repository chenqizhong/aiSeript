import os
import requests
from flask import Flask, request, abort
from openai import OpenAI
from google import genai
from google.genai import types

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

# 同時初始化兩個 AI 客戶端
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
gemini_client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))

@app.route("/", methods=['GET'])
def index():
    return "LINE Bot Dual-Core Failover Service is running!"

@app.route("/api/webhook", methods=['POST'])
def callback():
    body = request.get_json()
    
    if not body or 'events' not in body or len(body['events']) == 0:
        return 'OK'

    for event in body['events']:
        if event.get('type') == 'message' and event['message'].get('type') == 'text':
            reply_token = event['replyToken']
            raw_message = event['message']['text'].strip()
            
            # --- 🤖 關鍵過濾機制 (支援 Tag 標記) ---
            trigger_words = ("@腫忠ai機器人", "@腫忠", "@腫忠ai")
            has_trigger = any(raw_message.lower().startswith(word) for word in trigger_words)
            
            if not has_trigger:
                continue
                
            user_message = raw_message
            for word in trigger_words:
                if raw_message.lower().startswith(word):
                    user_message = raw_message[len(word):].strip()
                    break
            
            if not user_message:
                user_message = "嗨！點名我做什麼呢？有什麼我可以幫忙的？"
            # ------------------------------------

            reply_text = ""

            # 🚀 【第一層：主要挑戰】優先呼叫 OpenAI GPT
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "你是一個幽默、溫暖且非常有幫助的 LINE 智慧助理。"},
                        {"role": "user", "content": user_message}
                    ]
                )
                # 成功拿回 GPT 的回答，並在最下面新增模型標籤
                reply_text = response.choices[0].message.content + "\n\n(🧠 本訊息由 GPT 提供)"
                
            except Exception as gpt_error:
                # 🚨 當 GPT 免費流量滿了、扣款失敗或當機，會跳進這裡，自動啟動備援
                print(f"GPT 呼叫失敗: {str(gpt_error)}。自動切換至 Gemini...")
                
                # 🛠️ 【第二層：自動救援】呼叫 Google Gemini
                try:
                    response = gemini_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=user_message,
                        config=types.GenerateContentConfig(
                            system_instruction="你是一個幽默、溫暖且非常有幫助的 LINE 智慧助理。"
                        )
                    )
                    # 成功拿回 Gemini 的回答，並在最下面新增備援模型標籤
                    reply_text = response.text + "\n\n(🤖 本訊息由 Gemini 備援系統提供)"
                    
                except Exception as gemini_error:
                    # 萬一兩邊都一起出狀況的極端防錯
                    reply_text = f"糟糕，兩大 AI 大腦都打結了... (GPT 錯誤: {str(gpt_error)} / Gemini 錯誤: {str(gemini_error)})"

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