import csv
import re
import itertools

def extract_triples():
    print("正在加载核心实体字典...")
    # 1. 读取人工清洗好的高质量实体
    entities = []
    with open('core_entities.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # 跳过表头
        for row in reader:
            if row:
                entities.append(row[0]) # 只取第一列的实体名称
                
    print(f"成功加载 {len(entities)} 个核心实体。")

    # 2. 读取纯文本语料
    print("正在加载图灵生平语料...")
    with open('turing_corpus_clean.txt', 'r', encoding='utf-8') as f:
        text = f.read()

    # 3. 将整篇文章按句号、感叹号、问号切分成单句
    sentences = re.split(r'[。！？\n]', text)
    
    # 4. 定义关系触发词典（这就是人工注入的“知识工程规则”）
    relation_rules = {
        "出生": "出生于", "国籍": "国籍", "毒死": "死于", "氰化物": "死于",
        "就读": "就读于", "毕业": "就读于", "导师": "博士导师", 
        "任职": "任职于", "工作": "任职于", "加入": "任职于",
        "参与": "参与", "二战": "参与", "破解": "参与破解", "提出": "提出", "发表": "提出",
        "院士": "获选院士", "同事": "同事", "属于": "属于", "设立": "设立",
        "研究": "研究", "撰写": "撰写", "著作": "撰写"
    }

    triples = []
    print("正在逐句扫描并抽取实体关系...")
    
    # 5. 遍历每一句话
    for sentence in sentences:
        if not sentence.strip():
            continue
            
        # 找出这句话中包含了哪些字典里的实体
        found_entities = [ent for ent in entities if ent in sentence]
        
        # 如果一句话里至少有两个实体，就有可能存在关系
        if len(found_entities) >= 2:
            # 将句子里的实体两两配对组合
            pairs = list(itertools.combinations(found_entities, 2))
            
            for entity1, entity2 in pairs:
                # 默认关系是“相关”
                relation = "相关"
                
                # 检查句子里有没有定义的触发词
                for trigger_word, rel_name in relation_rules.items():
                    if trigger_word in sentence:
                        relation = rel_name
                        break # 找到一个具体关系就跳出

                # 把文本里的别名统一洗成标准名称
                alias_map = {
                    "图灵": "艾伦·图灵", "Turing": "艾伦·图灵",
                    "二战": "第二次世界大战", "剑桥": "剑桥大学",
                    "普林斯顿": "普林斯顿大学"
                }
                e1_clean = alias_map.get(entity1, entity1)
                e2_clean = alias_map.get(entity2, entity2)
                
                # 为了防止图谱里充斥太多无用的双向连线，稍微排个序再存入
                # 使用清洗后的标准名称存入三元组
                if "图灵" in e2_clean and "图灵" not in e1_clean:
                    triples.append([e2_clean, relation, e1_clean])
                else:
                    triples.append([e1_clean, relation, e2_clean])

    # 6. 去重并保存三元组
    unique_triples = []
    [unique_triples.append(t) for t in triples if t not in unique_triples]

    print("正在保存三元组数据...")
    with open('turing_triples.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['头实体', '关系', '尾实体'])
        writer.writerows(unique_triples)
        
    print(f"共抽取了 {len(unique_triples)} 条知识三元组。")

if __name__ == "__main__":
    extract_triples()