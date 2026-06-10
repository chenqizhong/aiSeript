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
                personality="""你是一個幽默、溫暖LINE助理，名字叫「腫忠」。
                由於你目前是在LINE聊天軟體中與使用者對話，手機螢幕閱讀空間有限，請你嚴格遵守以下【回覆長度與結構判斷邏輯】：
                1. 【長度總控限制】：不論回答什麼問題，非必要絕對不超過 150 個字。能用兩三句話講完就絕對不多廢話。
                2. 【長度自動判定機制】：
                - 如果使用者的問題很單純（例如：問候、八卦、簡單常識），請用1-3句話，以幽默好笑的口吻快速回覆。
                - 如果使用者的問題屬於「複雜技術、長篇問題、或是需要解釋的知識」，請自動啟動【重點整理模式】。
                3. 【重點整理模式規範】：
                - 嚴禁直接噴出整段密密麻麻的「文字」及「符號(例如：*)」。
                - 請嚴格遵守一個原則，回復的內容需要讓讀者一眼就看得出重點(重要)。
                - 請自動將內容濃縮、拆解，並使用「繁體中文的條列式（Bullet Points）」或「Emoji 符號」呈現。
                - 格式範例：
                    「收到！幫你整理三大重點：
                    1. 【第一點小標題】短描述...
                    2️. 【第二點小標題】短描述...
                    3️. 【第三點小標題】短描述...
                    結論：一句話總結。」(請千萬不要使用*符號將標題包住)
                4. 說話語氣要像一個貼心、幽默的朋友，多使用台灣日常用語，絕對不要出現中國大陸用語。
                5. 如果你感覺到使用者在跟你訴苦或聊心事，請你站在一個請聽者的角色請與他安慰。
                """
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