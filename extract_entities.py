import spacy
import csv

def extract_and_save_entities():
    print("正在加载 spaCy 中文 NLP 模型 (这可能需要几秒钟)...")
    nlp = spacy.load("zh_core_web_sm")
    
    print("正在读取图灵语料...")
    with open('turing_corpus_clean.txt', 'r', encoding='utf-8') as f:
        text = f.read()
        
    print("AI 正在阅读并进行命名实体识别 (NER)...")
    doc = nlp(text)
    
    target_labels = {'PERSON', 'ORG', 'GPE', 'LOC', 'EVENT'}
    
    entities = []
    for ent in doc.ents:
        if ent.label_ in target_labels:
            clean_text = ent.text.strip()
            if len(clean_text) > 1:
                label = "Location" if ent.label_ in ['GPE', 'LOC'] else ent.label_
                label = "Organization" if label == 'ORG' else label
                label = "Person" if label == 'PERSON' else label
                label = "Event" if label == 'EVENT' else label
                
                entities.append((clean_text, label))
                
    print("正在对实体进行去重...")
    # 利用 set() 自动剔除重复的 (实体名, 类型) 元组
    unique_entities = list(set(entities))
    
    # 按照实体类型排序
    unique_entities.sort(key=lambda x: (x[1], x[0]))
    
    print("正在保存纯净版实体表...")
    with open('core_entities.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['实体名称', '实体类型'])
        
        for ent_name, ent_type in unique_entities:
            writer.writerow([ent_name, ent_type])

    print(f"\n提取完成！共保存了 {len(unique_entities)} 个不重复的实体。")

if __name__ == "__main__":
    extract_and_save_entities()