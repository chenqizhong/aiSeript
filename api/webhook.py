import os
import requests
import re 
import redis  # 引入傳統正宗 Redis 驅動
from bs4 import BeautifulSoup 
from flask import Flask, request, abort
from openai import OpenAI
from google import genai
from google.genai import types

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

# 1. 初始化 OpenAI
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# 2. 初始化 Redis（從環境變數讀取你剛才拿到的 rediss:// 字串）
REDIS_URL = os.environ.get('REDIS_URL')
if REDIS_URL:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
else:
    redis_client = None
    print("[資管警告] 環境變數中找不到 REDIS_URL，機器人將在「無記憶模式」下運作！")


# ====== 【精準瘦身型網頁爬蟲函數】 ======
def fetch_web_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            main_content = soup.find(['article', 'main'])
            if main_content:
                paragraphs = main_content.find_all('p')
            else:
                paragraphs = soup.find_all('p')
            
            text_list = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            cleaned_text = "\n".join(text_list)
            return cleaned_text[:1200]  # 限制 1200 字防爆
        return f"[系統通知：無法讀取該網頁，錯誤代碼 {response.status_code}]"
    except Exception as e:
        return f"[系統通知：網頁讀取失敗，原因 {str(e)}]"


@app.route("/", methods=['GET'])
def index():
    return "LINE Bot Dual-Core Memory Service is running!"


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

            # =====================================================================
            # ====== 🧠 【動態辨識 USER 或 GROUP 並撈取歷史記憶】 ======
            # =====================================================================
            session_id = "default_session"
            source = event.get('source', {})
            
            if source.get('type') == 'group':
                session_id = f"group:{source.get('groupId')}"
            elif source.get('type') == 'room':
                session_id = f"room:{source.get('roomId')}"
            else:
                session_id = f"user:{source.get('userId')}"

            history_text = ""
            if redis_client:
                try:
                    chat_history = redis_client.lrange(session_id, 0, -1)
                    if chat_history:
                        history_text = "\n".join(chat_history)
                except Exception as redis_err:  # 🌟 已修正：不蓋掉全域 re 模組
                    print(f"[Redis 讀取失敗]: {redis_err}")

            # =====================================================================
            # ====== 🤖 【建構大腦 Prompt：完美融合歷史、目前問題、網頁爬蟲】 ======
            # =====================================================================
            prompt_parts = []
            
            if history_text:
                prompt_parts.append(f"【前情提要（這是你們過去的對話歷史，請作為上下文參考）】:\n{history_text}\n")
            
            prompt_parts.append(f"【最新使用者提問】: {user_message}")
            
            urls = re.findall(r'https?://[^\s]+', user_message)
            if urls:
                print(f"[系統進度] 偵測到網址，正在預先爬取: {urls[0]}")
                web_text = fetch_web_content(urls[0])
                prompt_parts.append(f"\n【附帶網頁內文（參考資料）】:\n{web_text}")
                
            final_ai_prompt = "\n".join(prompt_parts)
            # =====================================================================

            reply_text = ""

            # 🚀 【第一層】優先呼叫 Google Gemini
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
                1. 【(Emoji 符號)小標題】短描述...
                2. 【(Emoji 符號)小標題】短描述...
                結論：一句話總結。

                4.【終極警告】：
                你的輸出會直接顯示在沒有支援 Markdown 的環境。如果你的回答中出現任何一個「*」符號，系統就會出錯。請絕對不要使用「*」或「**」來加粗字體，請改用【】括號。"""

                gemini_key = os.environ.get('GEMINI_API_KEY')
                if not gemini_key:
                    raise ValueError("環境變數中找不到 GEMINI_API_KEY")
                
                gemini_client = genai.Client(api_key=gemini_key)
                
                # 🛠️ ====== 【核心優化：資管節流型動態搜尋過濾】 ======
                tools_list = None
                search_keywords = ["查", "搜尋", "網頁", "天氣", "新聞", "股價", "推薦", "什麼是", "誰是", "最新", "幾號", "今天", "明天"]
                
                # 只有當使用者的文字中含有特定搜尋關鍵字，才允許開起 Google 搜尋功能
                if any(kw in user_message for kw in search_keywords):
                    print(f"[資源控制] 偵測到連網需求關鍵字，為本次請求解鎖 Google Search 工具。")
                    tools_list = [types.Tool(google_search=types.GoogleSearch())]
                else:
                    print(f"[資源控制] 純聊天或翻閱記憶，保持離線文字模式（不消耗連網次數）。")
                # ====================================================

                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=final_ai_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=personality,
                        tools=tools_list  # 🌟 帶入動態決策後的工具清單
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
                            {"role": "system", "content": personality},
                            {"role": "user", "content": final_ai_prompt}
                        ]
                    )
                    reply_text = response.choices[0].message.content + "\n\n(GPT-4.0)"
                    
                except Exception as gpt_error:
                    reply_text = f"糟糕，兩大 AI 大腦都打結了... (Gemini 錯誤: {str(gemini_error)} / GPT 錯誤: {str(gpt_error)})"

            # =====================================================================
            # ====== 🧠 【AI 回覆成功後，將對話寫入 Redis 記憶】 ======
            # =====================================================================
            if redis_client and ("錯誤" not in reply_text and "大腦都打結" not in reply_text):
                try:
                    clean_reply = reply_text.replace("\n\n(Gemini-2.5)", "").replace("\n\n(GPT-4.0)", "")
                    
                    redis_client.rpush(session_id, f"User: {user_message}")
                    redis_client.rpush(session_id, f"AI: {clean_reply}")
                    
                    # 嚴格限制只保留最後 100 筆，舊的自動擠出去
                    redis_client.ltrim(session_id, -100, -1)
                    
                    # 設定 24 小時（86400秒）定時炸彈，一天沒聊天自動清空
                    redis_client.expire(session_id, 86400)
                except Exception as we:
                    print(f"[Redis 寫入失敗]: {we}")
            # =====================================================================

            # 3. 回傳給 LINE 官方伺服器
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