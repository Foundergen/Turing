import zhconv

def standardize_text():
    # 1. 读取爬取得到的混杂文本
    with open('turing_corpus.txt', 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    # 2. 将文本转化为简体中文 (zh-cn)
    print("正在进行简繁体转换...")
    clean_text = zhconv.convert(raw_text, 'zh-cn')
    
    # 3. 将干净的文本保存为一个新文件，供下一步抽取使用
    with open('turing_corpus_clean.txt', 'w', encoding='utf-8') as f:
        f.write(clean_text)
        
    print("清洗完成！已经生成全简体版本的 turing_corpus_clean.txt")
    
if __name__ == "__main__":
    standardize_text()