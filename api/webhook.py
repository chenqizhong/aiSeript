import os
import requests
from flask import Flask, request, abort
from openai import OpenAI
from google import genai
from google.genai import types

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

# 【注意】這裡絕對不能有 gemini_client = genai.Client(...) ！！！
# 唯獨保留 OpenAI 的初始化（若其套件允許空 key 傳入）
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route("/", methods=['GET'])
def index():
    return "LINE Bot Dual-Core Failover Service (Gemini Primary Safe Mode) is running!"

@app.route("/api/webhook", methods=['POST'])
def callback():
    body = request.get_json()
    
    if not body or 'events' not in body or len(body['events']) == 0:
        return 'OK'

    for event in body['events']:
        if event.get('type') == 'message' and event['message'].get('type') == 'text':
            reply_token = event['replyToken']
            raw_message = event['message']['text'].strip()
            
            # --- 🤖 關鍵過濾機制 (支援大寫與多種 Tag 標記) ---
            trigger_words = ("@ai", "@腫忠ai機器人", "@腫忠", "@腫忠ai")
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

            # 🚀 【第一層：主要挑戰】優先呼叫 Google Gemini (安全延後載入)
            try:
                gemini_key = os.environ.get('GEMINI_API_KEY')
                if not gemini_key:
                    raise ValueError("環境變數中找不到 GEMINI_API_KEY")
                
                # 正確的作法：只有在真的要處理訊息時，才在 function 內部初始化！
                gemini_client = genai.Client(api_key=gemini_key)
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一個幽默、溫暖且非常有幫助的 LINE 智慧助理，你的名字叫「腫忠」不需要每次開頭都介紹自己，你只要知道你叫腫忠就好了。"
                    )
                )
                reply_text = response.text + "\n\n(Gemini-2.5)"
                
            except Exception as gemini_error:
                print(f"Gemini 呼叫失敗: {str(gemini_error)}。自動切換至 GPT 備援...")
                
                # 🛠️ 【第二層：自動救援】呼叫 OpenAI GPT
                try:
                    response = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "你是一個幽默、溫慢且非常有幫助的 LINE 智慧助理，你的名字叫「腫忠」不需要每次開頭都介紹自己，你只要知道你叫腫忠就好了。"},
                            {"role": "user", "content": user_message}
                        ]
                    )
                    reply_text = response.choices[0].message.content + "\n\n(GPT-4.0)"
                    
                except Exception as gpt_error:
                    reply_text = f"糟糕，兩大 AI 大腦都打結了... (Gemini 錯誤: {str(gemini_error)} / GPT 錯誤: {str(gpt_error)})"

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