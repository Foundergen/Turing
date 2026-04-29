import requests
import json

def fetch_turing_api():
    # 维基百科官方开放的数据接口
    url = "https://zh.wikipedia.org/w/api.php"
    
    # 直接向服务器“点单”
    params = {
        "action": "query",
        "prop": "extracts",
        "titles": "艾伦·图灵",
        "explaintext": 1,  # 1表示去除所有HTML标签，只保留干干净净的纯文本
        "format": "json",  # 返回 JSON 格式
        "redirects": 1     # 如果有简繁体或别名重定向，服务器自动跳到正确的词条
    }

    headers = {
        "User-Agent": "Knowledge-Engineering-Student-Bot/1.0"
    }

    proxies = {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897"
    }

    try:
        print("正在呼叫维基百科官方接口...")
        # 发送请求
        response = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=10)
        response.raise_for_status()
        
        # 将返回的数据解析为 JSON 字典
        data = response.json()
        
        pages = data['query']['pages']
        page_id = list(pages.keys())[0]  # 获取页面唯一的 ID
        
        if page_id == "-1":
            print("未找到！")
            return
            
        corpus_text = pages[page_id]['extract']
        
        # 保存到本地文件
        with open('turing_corpus.txt', 'w', encoding='utf-8') as f:
            f.write(corpus_text)
            
        print("抓取成功！")
        print(f"共抓取了 {len(corpus_text)} 个字符。")
        print("\n前 100 个字 ")
        print(corpus_text[:100] + "...")

    except Exception as e:
        print(f"失败: {e}")

if __name__ == "__main__":
    fetch_turing_api()