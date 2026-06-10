import os
import requests
import re  
from bs4 import BeautifulSoup  
from flask import Flask, request, abort
from openai import OpenAI
from google import genai
from google.genai import types

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

# 唯獨保留 OpenAI 的初始化
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# =====================================================================
# ====== 【精準瘦身型網頁爬蟲函數】 =================================
# ====== 只抓取 p 標籤或文章主體，強制限流 1200 字，全力省流量 ======
# =====================================================================
def fetch_web_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 優先尋找標準的文章主體區塊（常見於現代新聞、技術部落格）
            main_content = soup.find(['article', 'main'])
            if main_content:
                paragraphs = main_content.find_all('p')
            else:
                # 如果網站寫法比較傳統，就抓取全網頁的所有段落 p 標籤
                paragraphs = soup.find_all('p')
            
            # 取出每個段落的純文字，並自動剔除空白行
            text_list = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            cleaned_text = "\n".join(text_list)
            
            # 嚴格限制只回傳前 1200 個字，防止 token 爆炸觸發 429
            return cleaned_text[:1200]
            
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
            
            # --- 🤖 關鍵過濾機制 ---
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

            # =====================================================================
            # ====== 【新架構優化：雙核心共用預爬蟲機制】 =============================
            # ====== 不管後面是走 Gemini 還是 GPT，只要有網址，Python 都在這裡先爬好 ======
            # =====================================================================
            final_ai_prompt = user_message
            urls = re.findall(r'https?://[^\s]+', user_message)
            if urls:
                print(f"[系統進度] 偵測到網址，正在預先爬取: {urls[0]}")
                web_text = fetch_web_content(urls[0])
                final_ai_prompt = f"【使用者提問】：{user_message}\n\n【附帶網頁內文（參考資料）】：\n{web_text}"
            # =====================================================================

            # 🚀 【第一層：主要挑戰】優先呼召 Google Gemini (安全延後載入)
            try:
                personality="""你是一個幽默、溫暖的 LINE 助理，名字叫「腫忠」。
                由於在 LINE 軟體中對話，手機螢幕空間有限，請嚴格遵守以下規則：
                1.【長度與口吻】：
                - 總字數絕對不超過 100 字。
                - 語氣像貼心、幽默的台灣朋友，多用台灣日常用語，嚴禁中國大陸用語。
                - 若使用者在訴苦或聊心事，請站在傾聽者的角色給予溫暖安慰。
                
                2.【複雜問題自動啟動：重點整理模式】：
                - 當問題需要解釋、推薦或屬於複雜技術時，必須使用以下「純文字格式」或「Emoji 符號」呈現，一眼看出重點。
                - 嚴禁使用任何 Markdown 語法（絕對不能出現 * 或 ** 符號）。

                3.【排版格式範例】（必須完全模仿此格式，不准加上任何星號）：
                收到！幫你整理幾大重點：
                1. 【小標題】短描述...
                2. 【小標題】短描述...
                結論：一句話總結。

                4.【終極警告】：
                你的輸出會直接顯示在沒有支援 Markdown 的環境。如果你的回答中出現任何一個「*」符號，系統就會出錯。請絕對不要使用「*」或「**」來加粗字體，請改用【】括號。"""
                
                gemini_key = os.environ.get('GEMINI_API_KEY')
                if not gemini_key:
                    raise ValueError("環境變數中找不到 GEMINI_API_KEY")
                
                gemini_client = genai.Client(api_key=gemini_key)
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=final_ai_prompt,  # ====== 啟動爬蟲function ======
                    config=types.GenerateContentConfig(
                        system_instruction = personality # ====== 【Gemini初始化宣告】 ======
                        ,tools=[types.Tool(google_search=types.GoogleSearch())]  # 使用者沒貼網址、只問時事時，就讓Gemini自己上網找 
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
                            {"role": "system", "content": personality},  # ====== 【GPT初始化宣告】 ======
                            {"role": "user", "content": final_ai_prompt}  # ====== GPT 備援直接共用同一個爬蟲function ======
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