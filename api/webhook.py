import os
import requests
import re  # ====== 【新功能：新增導入】引入正規表達式來偵測網址 ======
from bs4 import BeautifulSoup  # ====== 【新功能：新增導入】引入爬蟲解析庫 ======
from flask import Flask, request, abort
from openai import OpenAI
from google import genai
from google.genai import types

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

# 【注意】這裡絕對不能有 gemini_client = genai.Client(...) ！！！
# 唯獨保留 OpenAI 的初始化（若其套件允許空 key 傳入）
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


# =====================================================================
# ====== 【新功能：網頁文字爬蟲函數】 ===================================
# ====== 專門用來抓取使用者貼的網址，萃取純文字供 GPT 備援使用 ======
# =====================================================================
def fetch_web_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 剃除雜訊標籤
            for script in soup(["script", "style", "nav", "footer"]):
                script.extract()
            text = soup.get_text(separator="\n", strip=True)
            return text[:2500]  # 限制字數，避免 token 超量
        return f"[系統通知：無法讀取該網頁，錯誤代碼 {response.status_code}]"
    except Exception as e:
        return f"[系統通知：網頁讀取失敗，原因 {str(e)}]"
# =====================================================================


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
                    # ====== 【新功能：Gemini 聯網設定】 ======
                    # 這裡直接加上了 tools 參數，一秒啟動 Google 官方搜尋功能！
                    config=types.GenerateContentConfig(
                        system_instruction="你是一個幽默、溫暖且非常有幫助的 LINE 智慧助理，你的名字叫「腫忠」不需要每次開頭都介紹自己，你只要知道你叫腫忠就好了。",
                        tools=[{"google_search": {}}]
                    )
                    # ========================================
                )
                reply_text = response.text + "\n\n(Gemini-2.5)"
                
            except Exception as gemini_error:
                print(f"Gemini 呼叫失敗: {str(gemini_error)}。自動切換至 GPT 備援...")
                
                # 🛠️ 【第二層：自動救援】呼叫 OpenAI GPT
                try:
                    # ====== 【新功能：GPT 貼網址讀取增強】 ======
                    # 如果 Gemini 掛了換 GPT 上場，我們檢查使用者有沒有貼網址。如果有，爬蟲會先去咬內文
                    gpt_user_content = user_message
                    urls = re.findall(r'https?://[^\s]+', user_message)
                    if urls:
                        web_text = fetch_web_content(urls[0])
                        gpt_user_content = f"【使用者提問】：{user_message}\n\n【附帶網頁內文（參考資料）】：\n{web_text}"
                    # ==========================================

                    response = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "你是一個幽默、溫慢且非常有幫助的 LINE 智慧助理，你的名字叫「腫忠」不需要每次開頭都介紹自己，你只要知道你叫腫忠就好了。"},
                            {"role": "user", "content": gpt_user_content}  # ====== 【新功能改動：帶入可能含有網頁內容的 prompt】 ======
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