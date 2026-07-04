"""
Извлекает текст из PDF-учебников (доп. материалы) в чанки для RAG.
Результат: data/parsed/corpus.jsonl  [{source, page, text}]
Запуск (один раз, долго): python core/build_corpus.py
"""
import os
import json
import re

BASE = os.environ.get('CASE_DIR', '.') + '/Дополнительные материалы'
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "parsed", "corpus.jsonl")

# Короткие человекочитаемые имена источников.
SRC_NAMES = {
    "geokniga-tehnologiyaobogashcheniyapoleznyhiskopaemyh.pdf": "Технология обогащения полезных ископаемых",
    "geokniga-flotacionnye-metody-obogashcheniya_0.pdf": "Флотационные методы обогащения",
    "geokniga-metallurgiya-blagorodnyh-metallov_0.pdf": "Металлургия благородных металлов",
    "tehnologiya_izvlecheniya_zolota_i_serebra_iz_upornogo_zolotosoderzhaschego.pdf":
        "Извлечение золота и серебра из упорного сырья",
    "geokniga_lodeyshchikovvvtehnologiyaizvlecheniyazolotaiserebraizupornyh1.pdf":
        "Лодейщиков. Извлечение золота и серебра из упорных руд",
}


def chunk_text(text, size=900, overlap=150):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


def main():
    import pdfplumber
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n = 0
    with open(OUT, "w", encoding="utf-8") as out:
        for fn in os.listdir(BASE):
            if not fn.lower().endswith(".pdf"):
                continue
            src = SRC_NAMES.get(fn, fn)
            path = os.path.join(BASE, fn)
            print(f"parsing {fn} ...")
            try:
                with pdfplumber.open(path) as pdf:
                    for pno, page in enumerate(pdf.pages, 1):
                        try:
                            txt = page.extract_text() or ""
                        except Exception:
                            continue
                        for ch in chunk_text(txt):
                            if len(ch) < 120:
                                continue
                            out.write(json.dumps(
                                {"source": src, "page": pno, "text": ch},
                                ensure_ascii=False) + "\n")
                            n += 1
            except Exception as e:
                print(f"  skip {fn}: {e}")
    print(f"done: {n} chunks -> {OUT}")


if __name__ == "__main__":
    main()
